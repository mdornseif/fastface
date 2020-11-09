from typing import Tuple
import numpy as np

class Padding():

    def __init__(self, target_size:Tuple[int,int]=(640,640), pad_value:int=0):
        self.pad_value = pad_value
        self.target_size = target_size # w,h

    def __call__(self, img:np.ndarray, boxes:np.ndarray) -> Tuple[np.ndarray, np.ndarray]:

        h,w,c = img.shape
        tw,th = self.target_size

        pad_left = int((tw - w) // 2) + (tw-w) % 2
        pad_right = int((tw - w) // 2)
        if w > tw: pad_left,pad_right = 0,0
        
        pad_up = int((th - h) // 2) + (th-h) % 2
        pad_down = int((th - h) // 2)
        if h > th: pad_up,pad_down = 0,0

        nimg = np.ones((th,tw,c), dtype=img.dtype) * self.pad_value
        nimg[pad_up:th-pad_down, pad_left:tw-pad_right] = img

        nboxes = boxes.copy()
        if len(boxes.shape) == 2 and boxes.shape[0] > 0:
            nboxes[:, [0,2]] = boxes[:, [0,2]] + pad_left
            nboxes[:, [1,3]] = boxes[:, [1,3]] + pad_up

        return nimg, nboxes