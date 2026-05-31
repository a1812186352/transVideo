"""Signal layer: local frame/audio/text analysis."""


def __getattr__(name):
    """Lazy-import heavy signal-layer dependencies only when accessed."""
    if name == "FrameExtractor":
        from understanding.signal.frame_extractor import FrameExtractor as _cls
        return _cls
    if name == "OCRExtractor":
        from understanding.signal.ocr_extract import OCRExtractor as _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
