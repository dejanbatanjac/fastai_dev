#AUTOGENERATED! DO NOT EDIT! File to edit: dev/09_vision_augment.ipynb (unless otherwise specified).

__all__ = ['RandTransform', 'FlipItem', 'DihedralItem', 'clip_remove_empty', 'PadMode', 'CropPad', 'RandomCrop',
           'ResizeMethod', 'Resize', 'RandomResizedCrop', 'AffineCoordTfm', 'affine_mat', 'mask_tensor', 'flip_mat',
           'TensorTypes', 'Flip', 'dihedral_mat', 'Dihedral', 'rotate_mat', 'Rotate', 'zoom_mat', 'Zoom', 'find_coeffs',
           'apply_perspective', 'Warp', 'logit', 'LightingTfm', 'Brightness', 'Contrast', 'setup_aug_tfms',
           'aug_transforms']

#Cell
from ..torch_basics import *
from ..test import *
from ..data.all import *
from .core import *
from ..notebook.showdoc import show_doc

#Cell
from torch import stack, zeros_like as t0, ones_like as t1
from torch.distributions.bernoulli import Bernoulli

#Cell
class RandTransform(Transform):
    "A transform that before_call its state at each `__call__`, only applied on the training set"
    filt,do,nm,supports = 0,True,None,[]
    def __init__(self, p=1., nm=None, before_call=None, **kwargs):
        super().__init__(**kwargs)
        self.p,self.nm,self.before_call = p,nm,ifnone(before_call,self.before_call)

    def before_call(self, b, filt):
        "before_call the state for input `b`"
        self.do = random.random() < self.p

    def __call__(self, b, filt=None, **kwargs):
        self.before_call(b, filt=filt)
        return super().__call__(b, filt=filt, **kwargs) if self.do else b

    def encodes(self, x):
        if self.nm is None or type(x) not in self.supports: return x
        return getattr(x,self.nm)

#Cell
def _neg_axis(x, axis):
    x[...,axis] = -x[...,axis]
    return x

#Cell
@patch
def flip_lr(x:Image.Image): return x.transpose(Image.FLIP_LEFT_RIGHT)
@patch
def flip_lr(x:TensorImage): return x.flip(-1)
@patch
def flip_lr(x:TensorPoint): return _neg_axis(x, 0)
@patch
def flip_lr(x:TensorBBox):
    bb,lbl = x
    bb = _neg_axis(bb.view(-1,2), 0)
    return (bb.view(-1,4),lbl)

#Cell
class FlipItem(RandTransform):
    "Randomly flip with probability `p`"
    supports=[PILImage,TensorImage,TensorMask,TensorPoint,TensorBBox]
    def __init__(self, p=0.5): super().__init__(p=p,nm='flip_lr')

#Cell
@patch
def dihedral(x:PILImage, k): return x if k==0 else x.transpose(k-1)
@patch
def dihedral(x:TensorImage, k):
        if k in [1, 3, 4, 7]: x = x.flip(-1)
        if k in [2, 4, 5, 7]: x = x.flip(-2)
        if k in [3, 5, 6, 7]: x = x.transpose(-1,-2)
        return x
@patch
def dihedral(x:TensorPoint, k):
        if k in [1, 3, 4, 7]: x = _neg_axis(x, 0)
        if k in [2, 4, 5, 7]: x = _neg_axis(x, 1)
        if k in [3, 5, 6, 7]: x = x.flip(1)
        return x
@patch
def dihedral(x:TensorBBox, k):
        pnts = TensorPoint.dihedral(x[0].view(-1,2), k).view(-1,2,2)
        tl,br = pnts.min(dim=1)[0],pnts.max(dim=1)[0]
        return [torch.cat([tl, br], dim=1), x[1]]

#Cell
class DihedralItem(RandTransform):
    "Randomly flip with probability `p`"
    def __init__(self, p=0.5): super().__init__(p=p)

    def before_call(self, b, filt):
        super().before_call(b, filt)
        self.k = random.randint(0,7)

    def encodes(self, x:(PILImage,TensorImage,TensorMask,TensorPoint,TensorBBox)):
        return x.dihedral(self.k)

#Cell
def clip_remove_empty(bbox, label):
    "Clip bounding boxes with image border and label background the empty ones."
    bbox = torch.clamp(bbox, -1, 1)
    empty = ((bbox[...,2] - bbox[...,0])*(bbox[...,3] - bbox[...,1]) < 0.)
    if isinstance(label, torch.Tensor): label[empty] = 0
    else: label = [0 if m else l for l,m in zip(label,empty)]
    return (bbox, label)

#Cell
from torchvision.transforms.functional import pad as tvpad

#Cell
mk_class('PadMode', **{o:o.lower() for o in ['Zeros', 'Border', 'Reflection']},
         doc="All possible padding mode as attributes to get tab-completion and typo-proofing")

#Cell
_pad_modes = {'zeros': 'constant', 'border': 'edge', 'reflection': 'reflect'}

@patch
def _do_crop_pad(x:Image.Image, tl, sz, pad_mode=PadMode.Zeros, resize_mode=Image.BILINEAR, resize_to=None):
    if tl[0] > 0 or tl[1] > 0:
        # At least one dim is inside the image, so needs to be cropped
        cw,ch = max(tl[0],0),max(tl[1],0)
        fw,fh = min(cw+sz[0], x.size[0]),min(ch+sz[1], x.size[1])
        x = x.crop((cw, ch, fw, fh))
    if tl[0] < 0 or tl[1] < 0:
        # At least one dim is outside the image, so needs to be padded
        pw,ph = max(-tl[0],0),max(-tl[1],0)
        fw,fh = max(sz[0]-x.size[0]-pw,0),max(sz[1]-x.size[1]-ph,0)
        x = tvpad(x, (pw, ph, fw, fh), padding_mode=_pad_modes[pad_mode])
    if resize_to is not None: x = x.resize(resize_to, resize_mode)
    return x

@patch
def _do_crop_pad(x:TensorPoint, tl, sz, orig_sz, pad_mode=PadMode.Zeros):
    #assert pad_mode==PadMode.Zeros,"Only zero padding is supported for `TensorPoint` and `TensorBBox`"
    old_sz,new_sz,tl = map(lambda o: tensor(o).float(), (orig_sz,sz,tl))
    return TensorPoint((x + 1) * old_sz/new_sz - tl * 2/new_sz - 1)

@patch
def _do_crop_pad(x:TensorBBox, tl, sz, orig_sz, pad_mode=PadMode.Zeros):
    bbox,label = x
    bbox = TensorPoint._do_crop_pad(bbox.view(-1,2), tl, sz, orig_sz, pad_mode).view(-1,4)
    return TensorBBox(clip_remove_empty(bbox, label))

@patch
def crop_pad(x:Image.Image, sz, pad_mode=PadMode.Zeros, resize_mode=Image.BILINEAR, resize_to=None):
    if isinstance(sz,int): sz = (sz,sz)
    tl = ((x.size[0]-sz[0])//2, (x.size[1]-sz[1])//2)
    return x._do_crop_pad(tl, sz, pad_mode=pad_mode, resize_mode=resize_mode, resize_to=resize_to)

#Cell
class CropPad(RandTransform):
    "Center crop or pad an image to `size`"
    mode,mode_mask,order,final_size,filt = Image.BILINEAR,Image.NEAREST,5,None,None
    def __init__(self, size, pad_mode=PadMode.Zeros, **kwargs):
        super().__init__(**kwargs)
        if isinstance(size,int): size=(size,size)
        self.size,self.pad_mode = (size[1],size[0]),pad_mode

    def before_call(self, b, filt):
        self.do = True
        self.cp_size = self.size
        self.orig_size = (b[0] if isinstance(b, tuple) else b).size
        self.tl = ((self.orig_size[0]-self.cp_size[0])//2, (self.orig_size[1]-self.cp_size[1])//2)

    def _encode_pil(self, x, mode): return x._do_crop_pad(self.tl, self.cp_size, pad_mode=self.pad_mode, resize_mode=mode, resize_to=self.final_size)
    def encodes(self, x:PILImage): return self._encode_pil(x, self.mode)
    def encodes(self, x:PILMask):  return self._encode_pil(x, self.mode_mask)

    def _encode_tens(self, x): return x._do_crop_pad(self.tl, self.cp_size, self.orig_size, pad_mode=self.pad_mode)
    def encodes(self, x:(TensorBBox,TensorPoint)): return self._encode_tens(x)

#Cell
class RandomCrop(CropPad):
    "Randomly crop an image to `size`"
    def before_call(self, b, filt):
        super().before_call(b, filt)
        w,h = self.orig_size
        if not filt: self.tl = (random.randint(0,w-self.cp_size[0]), random.randint(0,h-self.cp_size[1]))

#Cell
mk_class('ResizeMethod', **{o:o.lower() for o in ['Squish', 'Crop', 'Pad']},
         doc="All possible resize method as attributes to get tab-completion and typo-proofing")

#Cell
class Resize(CropPad):
    order=10
    "Resize image to `size` using `method`"
    def __init__(self, size, method=ResizeMethod.Squish, pad_mode=PadMode.Reflection,
                 resamples=(Image.BILINEAR, Image.NEAREST), **kwargs):
        super().__init__(size, pad_mode=pad_mode, **kwargs)
        (self.mode,self.mode_mask),self.method = resamples,method

    def before_call(self, b, filt):
        super().before_call(b, filt)
        self.final_size = self.size
        if self.method==ResizeMethod.Squish:
            self.tl,self.cp_size = (0,0),self.orig_size
            return
        w,h = self.orig_size
        op = (operator.lt,operator.gt)[self.method==ResizeMethod.Pad]
        m = w/self.final_size[0] if op(w/self.final_size[0],h/self.final_size[1]) else h/self.final_size[1]
        self.cp_size = (int(m*self.final_size[0]),int(m*self.final_size[1]))
        if self.method==ResizeMethod.Pad or filt: self.tl = ((w-self.cp_size[0])//2, (h-self.cp_size[1])//2)
        else: self.tl = (random.randint(0,w-self.cp_size[0]), random.randint(0,h-self.cp_size[1]))

#Cell
class RandomResizedCrop(CropPad):
    "Picks a random scaled crop of an image and resize it to `size`"
    def __init__(self, size, min_scale=0.08, ratio=(3/4, 4/3), resamples=(Image.BILINEAR, Image.NEAREST), **kwargs):
        super().__init__(size, **kwargs)
        self.min_scale,self.ratio = min_scale,ratio
        self.mode,self.mode_mask = resamples

    def before_call(self, b, filt):
        super().before_call(b, filt)
        self.final_size = self.size
        w,h = self.orig_size
        for attempt in range(10):
            if filt: break
            area = random.uniform(self.min_scale,1.) * w * h
            ratio = math.exp(random.uniform(math.log(self.ratio[0]), math.log(self.ratio[1])))
            nw = int(round(math.sqrt(area * ratio)))
            nh = int(round(math.sqrt(area / ratio)))
            if nw <= w and nh <= h:
                self.cp_size = (nw,nh)
                self.tl = random.randint(0,w-nw), random.randint(0,h - nh)
                return
        if   w/h < self.ratio[0]: self.cp_size = (w, int(w/self.ratio[0]))
        elif w/h > self.ratio[1]: self.cp_size = (int(h*self.ratio[1]), h)
        else:                     self.cp_size = (w, h)
        self.tl = ((w-self.cp_size[0])//2, (h-self.cp_size[1])//2)

#Cell
def _init_mat(x):
    mat = torch.eye(3, dtype=x.dtype, device=x.device)
    return mat.unsqueeze(0).expand(x.size(0), 3, 3)

#Cell
@patch
def affine_coord(x: TensorImage, mat=None, coord_tfm=None, sz=None, mode='bilinear', pad_mode=PadMode.Reflection):
    if mat is None and coord_tfm is None: return x
    size = tuple(x.shape[-2:]) if sz is None else (sz,sz) if isinstance(sz,int) else tuple(sz)
    if mat is None: mat = _init_mat(x)[:,:2]
    coords = F.affine_grid(mat, x.shape[:2] + size)
    if coord_tfm is not None: coords = coord_tfm(coords)
    return TensorImage(F.grid_sample(x, coords, mode=mode, padding_mode=pad_mode))

@patch
def affine_coord(x: TensorMask, mat=None, coord_tfm=None, sz=None, mode='nearest', pad_mode=PadMode.Reflection):
    add_dim = (x.ndim==3)
    if add_dim: x = x[:,None]
    res = TensorImage.affine_coord(x.float(), mat, coord_tfm, sz, mode, pad_mode).long()
    if add_dim: res = res[:,0]
    return TensorMask(res)

@patch
def affine_coord(x: TensorPoint, mat=None, coord_tfm=None, sz=None, mode='nearest', pad_mode=PadMode.Zeros):
    #assert pad_mode==PadMode.Zeros, "Only zero padding is supported for `TensorPoint` and `TensorBBox`"
    if coord_tfm is not None: x = coord_tfm(x, invert=True)
    if mat is not None: x = (x - mat[:,:,2].unsqueeze(1)) @ torch.inverse(mat[:,:,:2].transpose(1,2))
    return TensorPoint(x)

@patch
def affine_coord(x: TensorBBox, mat=None, coord_tfm=None, sz=None, mode='nearest', pad_mode=PadMode.Zeros):
    if mat is None and coord_tfm is None: return x
    bbox,label = x
    bs,n = bbox.shape[:2]
    pnts = stack([bbox[...,:2], stack([bbox[...,0],bbox[...,3]],dim=2),
                  stack([bbox[...,2],bbox[...,1]],dim=2), bbox[...,2:]], dim=2)
    pnts = TensorPoint.affine_coord(pnts.view(bs, 4*n, 2), mat, coord_tfm, sz, mode, pad_mode)
    pnts = pnts.view(bs, n, 4, 2)
    tl,dr = pnts.min(dim=2)[0],pnts.max(dim=2)[0]
    return TensorBBox(clip_remove_empty(torch.cat([tl, dr], dim=2), label))

#Cell
class AffineCoordTfm(RandTransform):
    "Combine and apply affine and coord transforms"
    order = 30
    def __init__(self, aff_fs=None, coord_fs=None, size=None, mode='bilinear', pad_mode=PadMode.Reflection, mode_mask='nearest'):
        self.aff_fs,self.coord_fs = L(aff_fs),L(coord_fs)
        store_attr(self, 'size,mode,pad_mode,mode_mask')
        self.cp_size = None if size is None else (size,size) if isinstance(size, int) else tuple(size)

    def before_call(self, b, filt):
        if isinstance(b, tuple): b = b[0]
        self.do,self.mat = True,self._get_affine_mat(b)[:,:2]
        for t in self.coord_fs: t.before_call(b)

    def compose(self, tfm):
        "Compose `self` with another `AffineCoordTfm` to only do the interpolation step once"
        self.aff_fs   += tfm.aff_fs
        self.coord_fs += tfm.coord_fs

    def _get_affine_mat(self, x):
        aff_m = _init_mat(x)
        ms = [f(x) for f in self.aff_fs]
        ms = [m for m in ms if m is not None]
        for m in ms: aff_m = aff_m @ m
        return aff_m

    def _encode(self, x, mode, reverse=False):
        coord_func = None if len(self.coord_fs)==0 else partial(compose_tfms, tfms=self.coord_fs, reverse=reverse)
        return x.affine_coord(self.mat, coord_func, sz=self.size, mode=mode, pad_mode=self.pad_mode)

    def encodes(self, x:TensorImage): return self._encode(x, self.mode)
    def encodes(self, x:TensorMask):  return self._encode(x, self.mode_mask)
    def encodes(self, x:(TensorPoint, TensorBBox)): return self._encode(x, self.mode, reverse=True)

#Cell
def affine_mat(*ms):
    "Restructure length-6 vector `ms` into an affine matrix with 0,0,1 in the last line"
    return stack([stack([ms[0], ms[1], ms[2]], dim=1),
                  stack([ms[3], ms[4], ms[5]], dim=1),
                  stack([t0(ms[0]), t0(ms[0]), t1(ms[0])], dim=1)], dim=1)

#Cell
def mask_tensor(x, p=0.5, neutral=0.):
    "Mask elements of `x` with `neutral` with probability `1-p`"
    if p==1.: return x
    if neutral != 0: x.add_(-neutral)
    mask = x.new_empty(*x.size()).bernoulli_(p)
    x.mul_(mask)
    return x.add_(neutral) if neutral != 0 else x

#Cell
def flip_mat(x, p=0.5):
    "Return a random flip matrix"
    mask = mask_tensor(-x.new_ones(x.size(0)), p=p, neutral=1.)
    return affine_mat(mask,     t0(mask), t0(mask),
                      t0(mask), t1(mask), t0(mask))

#Cell
def _get_default(x, mode=None, pad_mode=None):
    if mode is None: mode='bilinear' if isinstance(x, TensorMask) else 'bilinear'
    if pad_mode is None: pad_mode=PadMode.Zeros if isinstance(x, (TensorPoint, TensorBBox)) else PadMode.Reflection
    x0 = x[0] if isinstance(x, tuple) else x
    return x0,mode,pad_mode

TensorTypes = (TensorImage,TensorMask,TensorPoint, TensorBBox)

#Cell
@patch
def flip_batch(x: TensorTypes, p=0.5, size=None, mode=None, pad_mode=None):
    x0,mode,pad_mode = _get_default(x, mode, pad_mode)
    return x.affine_coord(mat=flip_mat(x0, p=p)[:,:2], sz=size, mode=mode, pad_mode=pad_mode)

#Cell
def Flip(p=0.5, size=None, mode='bilinear', pad_mode=PadMode.Reflection):
    "Randomly flip a batch of images with a probability `p`"
    return AffineCoordTfm(aff_fs=partial(flip_mat, p=p), size=size, mode=mode, pad_mode=pad_mode)

#Cell
def _draw_mask(x, def_draw, draw=None, p=0.5, neutral=0.):
    if draw is None: draw=def_draw
    if callable(draw): return draw(x)
    elif is_listy(draw):
        test_eq(len(draw), x.size(0))
        res = tensor(draw, dtype=x.dtype, device=x.device)
    else: res = x.new_zeros(x.size(0)) + draw
    return mask_tensor(res, p=p, neutral=neutral)

#Cell
def dihedral_mat(x, p=0.5, draw=None):
    "Return a random dihedral matrix"
    def _def_draw(x): return torch.randint(0,8, (x.size(0),), device=x.device)
    idx = _draw_mask(x, _def_draw, draw=draw, p=p).long()
    xs = tensor([1,-1,1,-1,-1,1,1,-1], device=x.device).gather(0, idx)
    ys = tensor([1,1,-1,1,-1,-1,1,-1], device=x.device).gather(0, idx)
    m0 = tensor([1,1,1,0,1,0,0,0], device=x.device).gather(0, idx)
    m1 = tensor([0,0,0,1,0,1,1,1], device=x.device).gather(0, idx)
    return affine_mat(xs*m0,  xs*m1,  t0(xs),
                      ys*m1,  ys*m0,  t0(xs)).float()
    mask = mask_tensor(-x.new_ones(x.size(0)), p=p, neutral=1.)

#Cell
@patch
def dihedral_batch(x: TensorTypes, p=0.5, draw=None, size=None, mode=None, pad_mode=None):
    x0,mode,pad_mode = _get_default(x, mode, pad_mode)
    return x.affine_coord(mat=dihedral_mat(x0, p=p, draw=draw)[:,:2], sz=size, mode=mode, pad_mode=pad_mode)

#Cell
def Dihedral(p=0.5, draw=None, size=None, mode='bilinear', pad_mode=PadMode.Reflection):
    "Apply a random dihedral transformation to a batch of images with a probability `p`"
    return AffineCoordTfm(aff_fs=partial(dihedral_mat, p=p, draw=draw), size=size, mode=mode, pad_mode=pad_mode)

#Cell
def rotate_mat(x, max_deg=10, p=0.5, draw=None):
    "Return a random rotation matrix with `max_deg` and `p`"
    def _def_draw(x): return x.new(x.size(0)).uniform_(-max_deg, max_deg)
    thetas = _draw_mask(x, _def_draw, draw=draw, p=p) * math.pi/180
    return affine_mat(thetas.cos(), thetas.sin(), t0(thetas),
                     -thetas.sin(), thetas.cos(), t0(thetas))

#Cell
@delegates(rotate_mat)
@patch
def rotate(x: TensorTypes, size=None, mode=None, pad_mode=None, **kwargs):
    x0,mode,pad_mode = _get_default(x, mode, pad_mode)
    return x.affine_coord(mat=rotate_mat(x0, **kwargs)[:,:2], sz=size, mode=mode, pad_mode=pad_mode)

#Cell
def Rotate(max_deg=10, p=0.5, draw=None, size=None, mode='bilinear', pad_mode=PadMode.Reflection):
    "Apply a random rotation of at most `max_deg` with probability `p` to a batch of images"
    return AffineCoordTfm(partial(rotate_mat, max_deg=max_deg, p=p, draw=draw),
                          size=size, mode=mode, pad_mode=pad_mode)

#Cell
def zoom_mat(x, max_zoom=1.1, p=0.5, draw=None, draw_x=None, draw_y=None):
    "Return a random zoom matrix with `max_zoom` and `p`"
    def _def_draw(x):     return x.new(x.size(0)).uniform_(1, max_zoom)
    def _def_draw_ctr(x): return x.new(x.size(0)).uniform_(0,1)
    s = 1/_draw_mask(x, _def_draw, draw=draw, p=p, neutral=1.)
    col_pct = _draw_mask(x, _def_draw_ctr, draw=draw_x, p=1.)
    row_pct = _draw_mask(x, _def_draw_ctr, draw=draw_y, p=1.)
    col_c = (1-s) * (2*col_pct - 1)
    row_c = (1-s) * (2*row_pct - 1)
    return affine_mat(s,     t0(s), col_c,
                      t0(s), s,     row_c)

#Cell
@delegates(zoom_mat)
@patch
def zoom(x: TensorTypes, size=None, mode='bilinear', pad_mode=PadMode.Reflection, **kwargs):
    x0,mode,pad_mode = _get_default(x, mode, pad_mode)
    return x.affine_coord(mat=zoom_mat(x0, **kwargs)[:,:2], sz=size, mode=mode, pad_mode=pad_mode)

#Cell
def Zoom(max_zoom=1.1, p=0.5, draw=None, draw_x=None, draw_y=None, size=None, mode='bilinear',
         pad_mode=PadMode.Reflection):
    "Apply a random zoom of at most `max_zoom` with probability `p` to a batch of images"
    return AffineCoordTfm(partial(zoom_mat, max_zoom=max_zoom, p=p, draw=draw, draw_x=draw_x, draw_y=draw_y),
                          size=size, mode=mode, pad_mode=pad_mode)

#Cell
def find_coeffs(p1, p2):
    "Find coefficients for warp tfm from `p1` to `p2`"
    m = []
    p = p1[:,0,0]
    #The equations we'll need to solve.
    for i in range(p1.shape[1]):
        m.append(stack([p2[:,i,0], p2[:,i,1], t1(p), t0(p), t0(p), t0(p), -p1[:,i,0]*p2[:,i,0], -p1[:,i,0]*p2[:,i,1]]))
        m.append(stack([t0(p), t0(p), t0(p), p2[:,i,0], p2[:,i,1], t1(p), -p1[:,i,1]*p2[:,i,0], -p1[:,i,1]*p2[:,i,1]]))
    #The 8 scalars we seek are solution of AX = B
    A = stack(m).permute(2, 0, 1)
    B = p1.view(p1.shape[0], 8, 1)
    return torch.solve(B,A)[0]

#Cell
def apply_perspective(coords, coeffs):
    "Apply perspective tranfom on `coords` with `coeffs`"
    sz = coords.shape
    coords = coords.view(sz[0], -1, 2)
    coeffs = torch.cat([coeffs, t1(coeffs[:,:1])], dim=1).view(coeffs.shape[0], 3,3)
    coords = coords @ coeffs[...,:2].transpose(1,2) + coeffs[...,2].unsqueeze(1)
    coords.div_(coords[...,2].unsqueeze(-1))
    return coords[...,:2].view(*sz)

#Cell
class _WarpCoord():
    def __init__(self, magnitude=0.2, p=0.5, draw_x=None, draw_y=None):
        self.coeffs,self.magnitude,self.p,self.draw_x,self.draw_y = None,magnitude,p,draw_x,draw_y

    def _def_draw(self, x): return x.new(x.size(0)).uniform_(-self.magnitude, self.magnitude)
    def before_call(self, x):
        x_t = _draw_mask(x, self._def_draw, self.draw_x, p=self.p)
        y_t = _draw_mask(x, self._def_draw, self.draw_y, p=self.p)
        orig_pts = torch.tensor([[-1,-1], [-1,1], [1,-1], [1,1]], dtype=x.dtype, device=x.device)
        self.orig_pts = orig_pts.unsqueeze(0).expand(x.size(0),4,2)
        targ_pts = stack([stack([-1-y_t, -1-x_t]), stack([-1+y_t, 1+x_t]),
                          stack([ 1+y_t, -1+x_t]), stack([ 1-y_t, 1-x_t])])
        self.targ_pts = targ_pts.permute(2,0,1)

    def __call__(self, x, invert=False):
        coeffs = find_coeffs(self.targ_pts, self.orig_pts) if invert else find_coeffs(self.orig_pts, self.targ_pts)
        return apply_perspective(x, coeffs)

#Cell
@delegates(_WarpCoord.__init__)
@patch
def warp(x: TensorTypes, size=None, mode='bilinear', pad_mode=PadMode.Reflection, **kwargs):
    x0,mode,pad_mode = _get_default(x, mode, pad_mode)
    coord_tfm = _WarpCoord(**kwargs)
    coord_tfm.before_call(x0)
    return x.affine_coord(coord_tfm=coord_tfm, sz=size, mode=mode, pad_mode=pad_mode)

#Cell
def Warp(magnitude=0.2, p=0.5, draw_x=None, draw_y=None,size=None, mode='bilinear', pad_mode=PadMode.Reflection):
    "Apply perspective warping with `magnitude` and `p` on a batch of matrices"
    return AffineCoordTfm(coord_fs=_WarpCoord(magnitude=magnitude, p=p, draw_x=draw_x, draw_y=draw_y),
                          size=size, mode=mode, pad_mode=pad_mode)

#Cell
def logit(x):
    "Logit of `x`, clamped to avoid inf."
    x = x.clamp(1e-7, 1-1e-7)
    return -(1/x-1).log()

#Cell
@patch
def lighting(x: TensorImage, func):
    return TensorImage(torch.sigmoid(func(logit(x))))

#Cell
class LightingTfm(RandTransform):
    "Apply `fs` to the logits"
    order = 40
    def __init__(self, fs): self.fs=L(fs)
    def before_call(self, b, filt):
        self.do = True
        if isinstance(b, tuple): b = b[0]
        for t in self.fs: t.before_call(b)

    def compose(self, tfm):
        "Compose `self` with another `LightingTransform`"
        self.fs += tfm.fs

    def encodes(self,x:TensorImage): return x.lighting(partial(compose_tfms, tfms=self.fs))

#Cell
class _BrightnessLogit():
    def __init__(self, max_lighting=0.2, p=0.75, draw=None):
        self.max_lighting,self.p,self.draw = max_lighting,p,draw

    def _def_draw(self, x): return x.new(x.size(0)).uniform_(0.5*(1-self.max_lighting), 0.5*(1+self.max_lighting))

    def before_call(self, x):
        self.change = _draw_mask(x, self._def_draw, draw=self.draw, p=self.p, neutral=0.5)

    def __call__(self, x): return x.add_(logit(self.change[:,None,None,None]))

#Cell
@delegates(_BrightnessLogit.__init__)
@patch
def brightness(x: TensorImage, **kwargs):
    func = _BrightnessLogit(**kwargs)
    func.before_call(x)
    return x.lighting(func)

#Cell
def Brightness(max_lighting=0.2, p=0.75, draw=None):
    "Apply change in brightness of `max_lighting` to batch of images with probability `p`."
    return LightingTfm(_BrightnessLogit(max_lighting, p, draw))

#Cell
class _ContrastLogit():
    def __init__(self, max_lighting=0.2, p=0.75, draw=None):
        self.max_lighting,self.p,self.draw = max_lighting,p,draw

    def _def_draw(self, x):
        return torch.exp(x.new(x.size(0)).uniform_(math.log(1-self.max_lighting), -math.log(1-self.max_lighting)))

    def before_call(self, x):
        self.change = _draw_mask(x, self._def_draw, draw=self.draw, p=self.p, neutral=1.)

    def __call__(self, x): return x.mul_(self.change[:,None,None,None])

#Cell
@delegates(_ContrastLogit.__init__)
@patch
def contrast(x: TensorImage, **kwargs):
    func = _ContrastLogit(**kwargs)
    func.before_call(x)
    return x.lighting(func)

#Cell
def Contrast(max_lighting=0.2, p=0.75, draw=None):
    "Apply change in contrast of `max_lighting` to batch of images with probability `p`."
    return LightingTfm(_ContrastLogit(max_lighting, p, draw))

#Cell
def _compose_same_tfms(tfms):
    tfms = L(tfms)
    if len(tfms) == 0: return None
    res = tfms[0]
    for tfm in tfms[1:]: res.compose(tfm)
    return res

#Cell
def setup_aug_tfms(tfms):
    "Go through `tfms` and combines together affine/coord or lighting transforms"
    aff_tfms = [tfm for tfm in tfms if isinstance(tfm, AffineCoordTfm)]
    lig_tfms = [tfm for tfm in tfms if isinstance(tfm, LightingTfm)]
    others = [tfm for tfm in tfms if tfm not in aff_tfms+lig_tfms]
    aff_tfm,lig_tfm =  _compose_same_tfms(aff_tfms),_compose_same_tfms(lig_tfms)
    res = [aff_tfm] if aff_tfm is not None else []
    if lig_tfm is not None: res.append(lig_tfm)
    return res + others

#Cell
def aug_transforms(do_flip=True, flip_vert=False, max_rotate=10., max_zoom=1.1, max_lighting=0.2,
                   max_warp=0.2, p_affine=0.75, p_lighting=0.75, xtra_tfms=None,
                   size=None, mode='bilinear', pad_mode=PadMode.Reflection):
    "Utility func to easily create a list of flip, rotate, zoom, warp, lighting transforms."
    res,tkw = [],dict(size=size, mode=mode, pad_mode=pad_mode)
    if do_flip:    res.append(Dihedral(p=0.5, **tkw) if flip_vert else Flip(p=0.5, **tkw))
    if max_warp:   res.append(Warp(magnitude=max_warp, p=p_affine, **tkw))
    if max_rotate: res.append(Rotate(max_deg=max_rotate, p=p_affine, **tkw))
    if max_zoom>1: res.append(Zoom(max_zoom=max_zoom, p=p_affine, **tkw))
    if max_lighting:
        res.append(Brightness(max_lighting=max_lighting, p=p_lighting))
        res.append(Contrast(max_lighting=max_lighting, p=p_lighting))
    return setup_aug_tfms(res + L(xtra_tfms))