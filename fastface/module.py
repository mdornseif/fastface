import os
from typing import Dict, Union
import numpy as np
import torch
import torch.nn as nn
import pytorch_lightning as pl

from .api import (
    download_pretrained_model,
    list_pretrained_models
)

from .utils.config import (
    get_arch_cls
)

from .utils.visualize import draw_rects
from PIL import Image

class FaceDetector(pl.LightningModule):
    """Generic pl.LightningModule definition for face detection
    """

    def __init__(self, arch: nn.Module = None, hparams: Dict = None):
        super().__init__()
        self.save_hyperparameters(hparams)
        self.arch = arch
        self.__metrics = {}

    def add_metric(self, name: str, metric: pl.metrics.Metric):
        """Adds given metric with name key

        Args:
            name (str): name of the metric
            metric (pl.metrics.Metric): Metric object
        """
        # TODO add warnings if override happens
        self.__metrics[name] = metric

    def get_metrics(self) -> Dict[str, pl.metrics.Metric]:
        """Return metrics defined in the `FaceDetector` instance

        Returns:
            Dict[str, pl.metrics.Metric]: defined model metrics with names
        """
        return {k:v for k,v in self.__metrics.items()}

    # ! use forward only for inference not training
    @torch.no_grad()
    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        """batch of images with float and B x C x H x W shape

        Args:
            batch (torch.Tensor): torch.FloatTensor(B x C x H x W)

        Returns:
            torch.Tensor: preds with shape (N, 6);
                (1:4) xmin, ymin, xmax, ymax
                (4:5) score
                (5:6) batch idx
        """
        image_h = batch.size(2)
        image_w = batch.size(3)

        # apply preprocess
        batch, sf, pad = self.arch.preprocess(batch)

        # get logits
        logits = self.arch.forward(batch)
        # logits: torch.Tensor(B, C', N)

        # apply postprocess
        preds = self.arch.postprocess(logits)
        # preds: torch.Tensor(N, 6)

        # adjuts predictions
        ## fix padding
        preds[:, :4] = preds[:, :4] - pad[:2].repeat(2)
        ## fix scale
        preds[:, :4] = preds[:, :4] / (sf + 1e-16)
        ## fix boundaries
        preds[:, [0, 2]] = preds[:, [0, 2]].clamp(min=0, max=image_w)
        preds[:, [1, 3]] = preds[:, [1, 3]].clamp(min=0, max=image_h)

        return preds

    def training_step(self, batch, batch_idx):
        batch, targets = batch

        # compute logits
        logits = self.arch.forward(batch)

        # compute loss
        loss = self.arch.compute_loss(logits, targets, hparams=self.hparams)
        # loss: dict of losses or loss

        return loss

    def on_validation_epoch_start(self):
        for metric in self.__metrics.values():
            metric.reset()

    @torch.no_grad()
    def validation_step(self, batch, batch_idx):
        batch, targets = batch
        batch_size = batch.size(0)

        # compute logits
        logits = self.arch.forward(batch)

        # compute loss
        loss = self.arch.compute_loss(logits, targets,
            hparams=self.hparams)
        # loss: dict of losses or loss

        # compute predictions
        preds = self.arch.postprocess(logits)
        # preds: N,6 as x1,y1,x2,y2,score,batch_idx

        batch_preds = [preds[preds[:, 5] == batch_idx][:, :5].cpu() for batch_idx in range(batch_size)]
        batch_gt_boxes = [target["target_boxes"].cpu() for target in targets]

        self.debug_step(batch, batch_preds, batch_gt_boxes)

        for metric in self.__metrics.values():
            metric.update(
                batch_preds,
                batch_gt_boxes
            )

        return loss

    def debug_step(self, batch, batch_preds, batch_gt_boxes):
        for img, preds, gt_boxes in zip(batch, batch_preds, batch_gt_boxes):
            img = (img.permute(1, 2, 0).cpu() * 255).numpy().astype(np.uint8)
            preds = preds.cpu().long().numpy()
            gt_boxes = gt_boxes.cpu().long().numpy()
            img = draw_rects(img, preds[:, :4], color=(255, 0, 0))
            img = draw_rects(img, gt_boxes[:, :4], color=(0, 255, 0))
            pil_img = Image.fromarray(img)
            pil_img.show()
            if input("press `q` to exit") == "q":
                exit(0)

    def on_validation_epoch_end(self):
        for name, metric in self.__metrics.items():
            print(f"{name}: {metric.compute()}")

    def configure_optimizers(self):
        return self.arch.configure_optimizers(hparams=self.hparams)

    @classmethod
    def build(cls, arch: str, config: Union[str, Dict],
            hparams: Dict = {}, **kwargs) -> pl.LightningModule:
        """Classmethod for creating `fastface.FaceDetector` instance from scratch

        Args:
            arch (str): architecture name
            config (Union[str, Dict]): configuration name or configuration dictionary
            hparams (Dict, optional): hyper parameters for the model. Defaults to {}.

        Returns:
            pl.LightningModule: fastface.FaceDetector instance with random weights initialization
        """
        # TODO handle config

        # get architecture nn.Module class
        arch_cls = get_arch_cls(arch)

        # build nn.Module with given configuration
        arch_module = arch_cls(config=config, **kwargs)

        # add config and arch information to the hparams
        hparams.update({'config': config, 'arch': arch})

        # add kwargs to the hparams
        hparams.update({'kwargs': kwargs})

        # build pl.LightninModule with given architecture
        return cls(arch=arch_module, hparams=hparams)

    @classmethod
    def from_checkpoint(cls, ckpt_path: str, **kwargs) -> pl.LightningModule:
        """Classmethod for creating `fastface.FaceDetector` instance with given checkpoint weights

        Args:
            ckpt_path (str): file path of the checkpoint

        Returns:
            pl.LightningModule: fastface.FaceDetector instance with checkpoint weights
        """
        return cls.load_from_checkpoint(ckpt_path, map_location='cpu', **kwargs)

    @classmethod
    def from_pretrained(cls, model: str, target_path: str = None, **kwargs) -> pl.LightningModule:
        """Classmethod for creating `fastface.FaceDetector` instance with pretrained weights

        Args:
            model (str): pretrained model name.
            target_path (str, optional): path to check for model weights, if not given it will use cache path. Defaults to None.

        Returns:
            pl.LightningModule: fastface.FaceDetector instance with pretrained weights
        """
        if model in list_pretrained_models():
            model = download_pretrained_model(model, target_path=target_path)
        assert os.path.isfile(model), f"given {model} not found in the disk"
        return cls.from_checkpoint(model, **kwargs)

    def on_load_checkpoint(self, checkpoint: Dict):
        arch = checkpoint['hyper_parameters']['arch']
        config = checkpoint['hyper_parameters']['config']
        kwargs = checkpoint['hyper_parameters']['kwargs']

        # get architecture nn.Module class
        arch_cls = get_arch_cls(arch)

        # build nn.Module with given configuration
        self.arch = arch_cls(config=config, **kwargs)
