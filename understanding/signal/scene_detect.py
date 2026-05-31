"""Scene detection using PySceneDetect to produce candidate shot boundaries.

PySceneDetect internally uses OpenCV for frame processing; this module
exposes candidate boundaries that will later be validated against the
frame-difference curve for final cut-point confirmation.
"""

from typing import List, Optional
from scenedetect import open_video, SceneManager, ContentDetector


class SceneDetector:
    """Detects candidate shot boundaries using PySceneDetect.

    Attributes:
        threshold: Sensitivity threshold for ContentDetector (default 27.0).
        min_scene_len: Minimum scene length in frames (default 15).
    """

    def __init__(self, threshold: float = 27.0, min_scene_len: int = 15) -> None:
        self.threshold = threshold
        self.min_scene_len = min_scene_len

    def detect(self, video_path: str) -> List[float]:
        """Run PySceneDetect and return candidate boundary timestamps.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            List of timestamps (in seconds) where scene boundaries are detected.
        """
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(
            ContentDetector(threshold=self.threshold, min_scene_len=self.min_scene_len)
        )
        scene_manager.detect_scenes(video)

        scene_list = scene_manager.get_scene_list()
        boundaries: List[float] = []

        for scene in scene_list:
            start_time = scene[0].get_seconds()
            boundaries.append(start_time)

        return boundaries

    def detect_with_frame_numbers(
        self, video_path: str
    ) -> List[dict]:
        """Run PySceneDetect and return boundary info with frame numbers.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            List of dicts with keys: start_frame, start_time, end_frame, end_time.
        """
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(
            ContentDetector(threshold=self.threshold, min_scene_len=self.min_scene_len)
        )
        scene_manager.detect_scenes(video)

        scene_list = scene_manager.get_scene_list()
        boundaries: List[dict] = []

        for scene in scene_list:
            boundaries.append({
                "start_frame": scene[0].get_frames(),
                "start_time": scene[0].get_seconds(),
                "end_frame": scene[1].get_frames(),
                "end_time": scene[1].get_seconds(),
            })

        return boundaries
