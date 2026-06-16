from PIL import Image, ImageStat


def _rgb(value):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(channel))) for channel in value))


class ImageAnalysisService:
    def analyze_photo(self, image_file):
        image = Image.open(image_file).convert("RGB")
        image.thumbnail((256, 256))
        width, height = image.size

        face_box = (
            width // 4,
            height // 5,
            max(width // 4 + 1, width * 3 // 4),
            max(height // 5 + 1, height * 4 // 5),
        )
        hair_box = (width // 5, 0, max(width // 5 + 1, width * 4 // 5), max(1, height // 3))
        eye_box = (
            width // 4,
            height // 3,
            max(width // 4 + 1, width * 3 // 4),
            max(height // 3 + 1, height // 2),
        )
        lower_face_box = (
            width // 3,
            height // 2,
            max(width // 3 + 1, width * 2 // 3),
            max(height // 2 + 1, height * 4 // 5),
        )

        skin = ImageStat.Stat(image.crop(face_box)).median[:3]
        hair = ImageStat.Stat(image.crop(hair_box)).median[:3]
        eyes = ImageStat.Stat(image.crop(eye_box)).median[:3]
        lower = ImageStat.Stat(image.crop(lower_face_box)).mean[:3]
        hair_brightness = sum(hair) / 3
        lower_brightness = sum(lower) / 3
        face_ratio = height / max(width, 1)

        detected = {
            "skin_tone": _rgb(skin),
            "hair_color": _rgb(hair),
            "hair_presence": hair_brightness < 225,
            "hair_style_hint": "short" if face_ratio < 1.15 else "medium",
            "eye_color_hint": _rgb(eyes),
            "glasses_detected": False,
            "beard_detected": lower_brightness < (sum(skin) / 3) * 0.72,
            "face_shape_hint": "oval" if face_ratio > 1.05 else "round",
            "confidence_scores": {
                "skin_tone": 0.62,
                "hair_color": 0.55,
                "hair_presence": 0.5,
                "eye_color_hint": 0.35,
                "glasses_detected": 0.2,
                "beard_detected": 0.35,
                "face_shape_hint": 0.48,
            },
            "analyzer": "pillow-safe-heuristic",
        }
        return self._enhance_with_opencv(image, detected)

    def _enhance_with_opencv(self, image, detected):
        try:
            import cv2
            import numpy
        except ImportError:
            detected["analysis_notes"] = "OpenCV/MediaPipe unavailable; used safe Pillow heuristics."
            return detected

        rgb = numpy.array(image)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
        if len(faces):
            _, _, face_width, face_height = max(faces, key=lambda item: item[2] * item[3])
            ratio = face_height / max(face_width, 1)
            detected["face_shape_hint"] = "oval" if ratio > 1.12 else "round"
            detected["confidence_scores"]["face_shape_hint"] = 0.7
            detected["analyzer"] = "opencv-haar-plus-color-heuristics"
            detected["analysis_notes"] = "OpenCV detected a face; color/accessory values remain approximate."
        else:
            detected["analyzer"] = "opencv-no-face-plus-pillow-heuristics"
            detected["analysis_notes"] = "OpenCV was available but did not detect a clear frontal face."
        return detected
