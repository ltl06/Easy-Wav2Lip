import warnings
warnings.filterwarnings("ignore")

_sr_upsampler = None

def _get_upsampler():
    global _sr_upsampler
    if _sr_upsampler is None:
        try:
            from gfpgan import GFPGANer
            _sr_upsampler = GFPGANer(
                model_path='checkpoints/GFPGANv1.4.pth',
                upscale=1,
                arch='clean',
                channel_multiplier=2,
                bg_upsampler=None,
            )
        except ImportError:
            _sr_upsampler = False
    return _sr_upsampler


def load_sr():
    upsampler = _get_upsampler()
    if upsampler is False:
        return None
    return upsampler


def upscale(image, properties):
    if properties is None:
        return image
    _, _, output = properties.enhance(
        image, has_aligned=False, only_center_face=False, paste_back=True
    )
    return output
