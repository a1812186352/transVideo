"""Frame extraction from video using OpenCV.

Extracts specific frame indices from a video file and saves them as PNG images
for downstream vision analysis (OCR, scene understanding, etc.).
"""

import logging
import os
from typing import List

import cv2

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Extract individual frames from a video file as PNG images.

    Used between the adaptive sampler and the vision analyzer in the pipeline.
    The sampler produces frame indices, this module extracts the actual images,
    and the vision analyzer processes those images.

    Attributes:
        work_dir: Root directory for output. Frame images are written to
            ``{work_dir}/frames/{video_id}/``.
    """

    def __init__(self, work_dir: str = "", downscale: bool = True) -> None:
        self.work_dir = work_dir
        self.downscale = downscale  # analyze at 480p for speed

    def extract(
        self, video_path: str, frame_indices: List[int], video_id: str = ""
    ) -> List[str]:
        """Extract specified frame indices from a video and save as PNG files.

        Args:
            video_path: Absolute path to the input video file.
            frame_indices: List of zero-based frame indices to extract.
            video_id: Identifier for the video, used as the output subdirectory
                name. Defaults to ``""`` (frames go directly under
                ``{work_dir}/frames/``).

        Returns:
            List of absolute paths to the extracted PNG frame images, in the
            same order as the input frame_indices. Frames that could not be
            read are excluded (a warning is logged for each failure).

        Raises:
            FileNotFoundError: If video_path does not exist or cannot be opened.
        """
        # Build output directory
        output_dir = os.path.join(self.work_dir, "frames", video_id)
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        extracted_paths: List[str] = []

        try:
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()

                if not ret or frame is None:
                    logger.warning(
                        "Failed to read frame %d from %s", idx, video_path
                    )
                    continue

                filename = f"frame_{idx:06d}.png"
                filepath = os.path.join(output_dir, filename)
                if self.downscale and frame.shape[1] > 854:
                    h = int(frame.shape[0] * 854 / frame.shape[1])
                    frame = cv2.resize(frame, (854, h), interpolation=cv2.INTER_AREA)
                cv2.imwrite(filepath, frame)
                extracted_paths.append(os.path.abspath(filepath))

        finally:
            cap.release()

        return extracted_paths
