import cv2


class MotionDetector:
    def __init__(self, sensitivity: int = 500):
        self.sensitivity = sensitivity
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=False
        )

    def detect(self, frame) -> tuple[bool, object]:
        """
        Returns (motion_detected, largest_contour).
        Motion is detected if any contour exceeds the sensitivity threshold.
        """
        fg_mask = self.subtractor.apply(frame)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        largest = None
        max_area = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > self.sensitivity and area > max_area:
                max_area = area
                largest = contour

        return largest is not None, largest
