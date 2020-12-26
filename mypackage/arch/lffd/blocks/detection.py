import torch
import torch.nn as nn
import torch.nn.functional as F

from typing import Tuple,List
from .conv import conv1x1
from mypackage.utils.matcher import LFFDMatcher
from mypackage.utils.utils import random_sample_selection

class DetectionHead(nn.Module):
    def __init__(self, head_idx:int, infeatures:int,
            features:int, rf_size:int, rf_start_offset:int, rf_stride:int,
            lower_scale:int, upper_scale:int, num_classes:int=2):

        super(DetectionHead,self).__init__()
        self.head_idx = head_idx
        self.rf_size = rf_size
        self.rf_start_offset = rf_start_offset
        self.rf_stride = rf_stride
        self.num_classes = num_classes

        self.det_conv = nn.Sequential(
            conv1x1(infeatures, features), nn.ReLU())

        self.cls_head = nn.Sequential(
            conv1x1(features, features),
            nn.ReLU(),
            conv1x1(features, self.num_classes))

        self.reg_head = nn.Sequential(
            conv1x1(features, features),
            nn.ReLU(),
            conv1x1(features, 4))

        def conv_xavier_init(m):
            if type(m) == nn.Conv2d:
                nn.init.xavier_normal_(m.weight)

                if m.bias is not None:
                    m.bias.data.fill_(0)

        self.apply(conv_xavier_init)

        self.matcher = LFFDMatcher(lower_scale,upper_scale)

    def apply_bbox_regression(self, reg_logits:torch.Tensor) -> torch.Tensor:
        """Applies bounding box regression using regression logits
        Args:
            reg_logits (torch.Tensor): bs,fh,fw,4

        Returns:
            pred_boxes (torch.Tensor): bs,fh,fw,4 as xmin,ymin,xmax,ymax
        """
        fh,fw = reg_logits.shape[1:3]

        rf_anchors = self.gen_rf_anchors(fh,fw,
            device=reg_logits.device,
            dtype=reg_logits.dtype)
        # rf_anchors: fh,fw,4
        rf_normalizer = self.rf_size/2
        assert fh == rf_anchors.size(0)
        assert fw == rf_anchors.size(1)

        rf_centers = (rf_anchors[:,:, :2] + rf_anchors[:,:, 2:]) / 2

        pred_boxes = reg_logits.clone()

        pred_boxes[:, :, :, 0] = rf_centers[:, :, 0] - (rf_normalizer*reg_logits[:, :, :, 0])
        pred_boxes[:, :, :, 1] = rf_centers[:, :, 1] - (rf_normalizer*reg_logits[:, :, :, 1])
        pred_boxes[:, :, :, 2] = rf_centers[:, :, 0] - (rf_normalizer*reg_logits[:, :, :, 2])
        pred_boxes[:, :, :, 3] = rf_centers[:, :, 1] - (rf_normalizer*reg_logits[:, :, :, 3])

        pred_boxes[:,:,:,[0,2]] = torch.clamp(pred_boxes[:,:,:,[0,2]],0,fw*self.rf_stride)
        pred_boxes[:,:,:,[1,3]] = torch.clamp(pred_boxes[:,:,:,[1,3]],0,fh*self.rf_stride)

        return pred_boxes

    def gen_rf_anchors(self, fmaph:int, fmapw:int, device:str='cpu',
            dtype:torch.dtype=torch.float32, clip:bool=False) -> torch.Tensor:
        """takes feature map h and w and reconstructs rf anchors as tensor

        Args:
            fmaph (int): featuremap hight
            fmapw (int): featuremap width
            device (str, optional): selected device to anchors will be generated. Defaults to 'cpu'.
            dtype (torch.dtype, optional): selected dtype to anchors will be generated. Defaults to torch.float32.
            clip (bool, optional): if True clips regions. Defaults to False.

        Returns:
            torch.Tensor: rf anchors as fmaph x fmapw x 4 (xmin, ymin, xmax, ymax)
        """

        # y: fmaph x fmapw
        # x: fmaph x fmapw
        y,x = torch.meshgrid(
            torch.arange(fmaph, dtype=dtype, device=device),
            torch.arange(fmapw, dtype=dtype, device=device)
        )

        # rfs: fmaph x fmapw x 2
        rfs = torch.stack([x,y], dim=-1)

        rfs *= self.rf_stride
        rfs += self.rf_start_offset

        # rfs: fh x fw x 2 as x,y
        rfs = rfs.repeat(1,1,2) # fh x fw x 2 => fh x fw x 4
        rfs[:,:,:2] = rfs[:,:,:2] - self.rf_size/2
        rfs[:,:,2:] = rfs[:,:,2:] + self.rf_size/2

        if clip:
            rfs[:,:,[0,2]] = torch.clamp(rfs[:,:,[0,2]],0,fmapw*self.rf_stride)
            rfs[:,:,[1,3]] = torch.clamp(rfs[:,:,[1,3]],0,fmaph*self.rf_stride)

        return rfs

    def build_targets(self, fmap:Tuple[int,int], gt_boxes:List[torch.Tensor], device:str='cpu',
            dtype:torch.dtype=torch.float32) -> Tuple[torch.Tensor,torch.Tensor,torch.Tensor,torch.Tensor,torch.Tensor]:
        """[summary]

        Args:
            fmap (Tuple[int,int]): fmap_h and fmap_w
            gt_boxes (List[torch.Tensor]): [N',4] as xmin,ymin,xmax,ymax
            device (str, optional): target device. Defaults to 'cpu'.
            dtype (torch.dtype, optional): target dtype. Defaults to torch.float32.

        Returns:
            Tuple[torch.Tensor,torch.Tensor,torch.Tensor,torch.Tensor,torch.Tensor]: [description]
        """
        # t_cls          : bs,fh',fw'      | type: model.dtype          | device: model.device
        # t_regs         : bs,fh',fw',4    | type: model.dtype          | device: model.device
        # ig             : bs,fh',fw'      | type: torch.bool           | device: model.device
        batch_size = len(gt_boxes)
        fh,fw = fmap

        t_cls = torch.zeros(*(batch_size,fh,fw), dtype=dtype, device=device)
        t_regs = torch.zeros(*(batch_size,fh,fw,4), dtype=dtype, device=device)
        ignore = torch.zeros(*(batch_size,fh,fw), dtype=torch.bool, device=device)

        # TODO cache rf anchors
        rf_anchors = self.gen_rf_anchors(fh, fw, device=device, dtype=dtype)

        # rf_anchors: fh x fw x 4 as xmin,ymin,xmax,ymax
        for i in range(batch_size):
            cls_mask,reg_targets,ignore_mask = self.matcher(rf_anchors,
                gt_boxes[i], self.rf_size/2, device=device, dtype=dtype)

            t_cls[i, cls_mask] = 1

            t_regs[i, :,:,:] = reg_targets
            ignore[i, :,:] = ignore_mask

        return t_cls,t_regs,ignore

    def forward(self, x:torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        data = self.det_conv(x)

        cls_logits = self.cls_head(data)
        # (b,c,h,w)
        reg_logits = self.reg_head(data)
        # (b,c,h,w)
        return cls_logits,reg_logits

    def compute_loss(self, cls_logits:torch.Tensor, reg_logits:torch.Tensor,
            gt_boxes:List[torch.Tensor]) -> Tuple[torch.Tensor,torch.Tensor]:
        fh,fw = cls_logits.shape[2:]
        device = cls_logits.device
        dtype = cls_logits.dtype
        batch_size = cls_logits.size(0)
        ratio = 5

        cls_logits = cls_logits.permute(0,2,3,1)
        reg_logits = reg_logits.permute(0,2,3,1)
        target_cls, target_regs, ignore = self.build_targets((fh,fw), gt_boxes, device=device, dtype=dtype)
        # target_cls     : bs,fh,fw      | type: model.dtype          | device: model.device
        # target_regs    : bs,fh,fw,4    | type: model.dtype          | device: model.device
        # ignore         : bs,fh,fw      | type: torch.bool           | device: model.device
        """
            16 torch.Size([20, 4])
            cls_logits:  torch.Size([16, 160, 160, 1])
            reg_logits:  torch.Size([16, 160, 160, 4])
            target_cls:  torch.Size([16, 160, 160])
            target_regs: torch.Size([16, 160, 160, 4])
            ignore:  torch.Size([16, 160, 160]
        """
        pos_mask = (target_cls == 1) & (~ignore)
        rpos_mask = target_cls == 1
        neg_mask = (target_cls == 0) & (~ignore)
        positives = pos_mask.sum()
        if positives <= 0:
            negatives = batch_size
        else:
            negatives = min(neg_mask.sum(), ratio*positives)

        # *Random sample selection
        ############################
        neg_mask = neg_mask.view(-1)
        ss, = torch.where(neg_mask)
        selections = random_sample_selection(ss.cpu().numpy().tolist(), negatives)
        neg_mask[:] = False
        neg_mask[selections] = True
        neg_mask = neg_mask.view(batch_size,fh,fw)
        negatives = neg_mask.sum()
        ###########################

        cls_loss = F.binary_cross_entropy_with_logits(
            cls_logits[pos_mask | neg_mask], target_cls[pos_mask | neg_mask].unsqueeze(-1))

        if rpos_mask.sum() <= 0:
            reg_loss = torch.tensor(0, dtype=dtype, device=device, requires_grad=True)
        else:
            reg_loss = F.mse_loss(reg_logits[rpos_mask], target_regs[rpos_mask])

        return cls_loss,reg_loss