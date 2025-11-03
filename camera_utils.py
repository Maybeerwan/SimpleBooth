import cv2
import threading
import time
import logging
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def detect_cameras():
    """Detect available USB cameras."""
    available_cameras = []
    logger.info("[CAMERA] Début de la détection des caméras USB...")

    for i in range(10):
        try:
            logger.info(f"[CAMERA] Test de la caméra ID {i}...")
            backends = [cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_V4L2, cv2.CAP_GSTREAMER]
            cap = None
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(i, backend)
                    if cap.isOpened():
                        resolutions_to_test = [
                            (1920, 1080),
                            (1280, 720),
                            (640, 480)
                        ]
                        best_resolution = None
                        best_fps = 0
                        for test_width, test_height in resolutions_to_test:
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, test_width)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, test_height)
                            cap.set(cv2.CAP_PROP_FPS, 30)
                            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            actual_fps = cap.get(cv2.CAP_PROP_FPS)
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.shape[1] >= test_width * 0.9 and frame.shape[0] >= test_height * 0.9:
                                best_resolution = (actual_width, actual_height)
                                best_fps = actual_fps
                                logger.info(f"[CAMERA] Résolution {actual_width}x{actual_height} supportée pour la caméra {i}")
                                break
                            else:
                                logger.info(f"[CAMERA] Résolution {test_width}x{test_height} non supportée pour la caméra {i}")
                        if best_resolution:
                            width, height = best_resolution
                            fps = best_fps
                            backend_name = {
                                cv2.CAP_ANY: "Auto",
                                cv2.CAP_DSHOW: "DirectShow",
                                cv2.CAP_V4L2: "V4L2",
                                cv2.CAP_GSTREAMER: "GStreamer",
                            }.get(backend, "Inconnu")
                            name = f"Caméra {i} ({backend_name}) - {width}x{height}@{fps:.1f}fps"
                            available_cameras.append((i, name))
                            logger.info(f"[CAMERA] ✓ Caméra fonctionnelle détectée: {name}")
                            break
                        else:
                            backend_name = {
                                cv2.CAP_ANY: "Auto",
                                cv2.CAP_DSHOW: "DirectShow",
                                cv2.CAP_V4L2: "V4L2",
                                cv2.CAP_GSTREAMER: "GStreamer",
                            }.get(backend, "Inconnu")
                            logger.info(f"[CAMERA] Caméra {i} ouverte mais ne peut pas lire de frame avec backend {backend_name}")
                    if cap is not None:
                        cap.release()
                except Exception as e:
                    if cap is not None:
                        cap.release()
                    logger.info(f"[CAMERA] Backend {backend} échoué pour caméra {i}: {e}")
                    continue
            if not available_cameras or available_cameras[-1][0] != i:
                logger.info(f"[CAMERA] ✗ Caméra {i} non disponible ou non fonctionnelle")
        except Exception as e:
            logger.info(f"[CAMERA] Erreur générale lors de la détection de la caméra {i}: {e}")
    logger.info(f"[CAMERA] Détection terminée. {len(available_cameras)} caméra(s) fonctionnelle(s) trouvée(s)")
    return available_cameras


class UsbCamera:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.camera = None
        self.is_running = False
        self.thread = None
        self.frame = None
        self.lock = threading.Lock()
        self.error = None

    def start(self):
        if self.is_running:
            return True
        return self._initialize_camera()

    def _initialize_camera(self):
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY, cv2.CAP_V4L2, cv2.CAP_GSTREAMER]
        for backend in backends:
            try:
                backend_name = {
                    cv2.CAP_ANY: "Auto",
                    cv2.CAP_DSHOW: "DirectShow",
                    cv2.CAP_V4L2: "V4L2",
                    cv2.CAP_GSTREAMER: "GStreamer",
                }.get(backend, "Inconnu")
                logger.info(f"[USB CAMERA] Tentative d'ouverture de la caméra {self.camera_id} avec backend {backend_name}...")
                self.camera = cv2.VideoCapture(self.camera_id, backend)
                if not self.camera.isOpened():
                    logger.info(f"[USB CAMERA] Backend {backend_name} : impossible d'ouvrir la caméra {self.camera_id}")
                    if self.camera is not None:
                        self.camera.release()
                    continue
                resolutions_to_test = [
                    (1920, 1080, "Full HD"),
                    (1280, 720, "HD"),
                    (640, 480, "VGA"),
                ]
                best_resolution = None
                for test_width, test_height, res_name in resolutions_to_test:
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, test_width)
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, test_height)
                    self.camera.set(cv2.CAP_PROP_FPS, 25)
                    actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
                    ret, frame = self.camera.read()
                    if ret and frame is not None and frame.shape[1] >= test_width * 0.9 and frame.shape[0] >= test_height * 0.9:
                        best_resolution = (actual_width, actual_height, actual_fps, res_name)
                        logger.info(
                            f"[USB CAMERA] Résolution {res_name} ({actual_width}x{actual_height}@{actual_fps:.1f}fps) configurée avec succès"
                        )
                        break
                    else:
                        logger.info(f"[USB CAMERA] Résolution {res_name} ({test_width}x{test_height}) non supportée")
                if not best_resolution:
                    logger.info(f"[USB CAMERA] Backend {backend_name} : aucune résolution fonctionnelle trouvée")
                    if self.camera is not None:
                        self.camera.release()
                    continue
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    logger.info(
                        f"[USB CAMERA] Backend {backend_name} : la caméra {self.camera_id} ne retourne pas d'image de manière stable"
                    )
                    if self.camera is not None:
                        self.camera.release()
                    continue
                self.is_running = True
                self.thread = threading.Thread(target=self._capture_loop)
                self.thread.daemon = True
                self.thread.start()
                logger.info(f"[USB CAMERA] Caméra {self.camera_id} démarrée avec succès via backend {backend_name}")
                return True
            except Exception as e:
                logger.info(f"[USB CAMERA] Erreur avec backend {backend_name}: {e}")
                if self.camera is not None:
                    self.camera.release()
                continue
        self.error = f"Impossible d'ouvrir la caméra {self.camera_id} avec tous les backends testés"
        logger.info(f"[USB CAMERA] Erreur: {self.error}")
        return False

    def _reconnect(self):
        logger.info(f"[USB CAMERA] Tentative de reconnexion de la caméra {self.camera_id}...")
        if self.camera is not None:
            self.camera.release()
        self.camera = None
        time.sleep(1)
        return self._initialize_camera()

    def _capture_loop(self):
        consecutive_errors = 0
        max_errors = 10
        while self.is_running:
            try:
                if self.camera is None or not self.camera.isOpened():
                    logger.info(f"[USB CAMERA] Caméra {self.camera_id} déconnectée, tentative de reconnexion...")
                    self._reconnect()
                    time.sleep(1)
                    continue
                ret, frame = self.camera.read()
                if ret:
                    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    with self.lock:
                        self.frame = jpeg.tobytes()
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    logger.info(f"[USB CAMERA] Erreur de lecture de frame (tentative {consecutive_errors}/{max_errors})")
                    if consecutive_errors >= max_errors:
                        logger.info(f"[USB CAMERA] Trop d'erreurs consécutives, tentative de reconnexion...")
                        self._reconnect()
                        consecutive_errors = 0
                time.sleep(0.03)
            except Exception as e:
                consecutive_errors += 1
                logger.info(f"[USB CAMERA] Erreur de capture: {e} (tentative {consecutive_errors}/{max_errors})")
                if consecutive_errors >= max_errors:
                    logger.info(f"[USB CAMERA] Trop d'erreurs consécutives, tentative de reconnexion...")
                    self._reconnect()
                    consecutive_errors = 0
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.frame

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.camera is not None:
            self.camera.release()
        logger.info(f"[USB CAMERA] Caméra {self.camera_id} arrêtée")


class MyPicammera:
    def __init__(
        self,
        resolution: Tuple[int, int] = (1280, 720),
        framerate: int = 15,
        qr_enabled: bool = False,
        qr_callback: Optional[callable] = None,
        detect_every_n_frames: int = 5,
        detect_downscale_width: int = 640,
        qr_debounce_seconds: float = 2.0,
    ):
        """
        Implémentation Picamera2 :
        - configure Picamera2 pour renvoyer des tableaux RGB
        - start() lance la capture en thread
        - options QR : qr_enabled, qr_callback(data, points)
        """
        self.resolution = resolution
        self.framerate = framerate
        self.picam2 = None
        self.is_running = False
        self.thread = None
        self.frame = None
        self.lock = threading.Lock()
        self.error = None

        # QR settings
        self.qr_enabled = qr_enabled
        self.qr_callback = qr_callback
        self.detect_every_n_frames = max(1, int(detect_every_n_frames))
        self.detect_downscale_width = max(32, int(detect_downscale_width))
        self.qr_debounce_seconds = float(qr_debounce_seconds)
        self._frame_count = 0
        self._last_qr = None
        self._last_qr_ts = 0.0
        self.qr_detector = None

        try:
            from picamera2 import Picamera2
            self.picam2 = Picamera2()
            # Configuration simple pour preview/still en RGB
            try:
                cfg = self.picam2.create_preview_configuration(main={"size": self.resolution, "format": "RGB888"})
            except Exception:
                cfg = self.picam2.create_still_configuration(main={"size": self.resolution, "format": "RGB888"})
            self.picam2.configure(cfg)
        except Exception as e:
            self.picam2 = None
            self.error = f"Picamera2 unavailable: {e}"
            logger.info(f"[PICAM] Erreur d'initialisation Picamera2: {e}")

        self.enable_qr_detection(qr_enabled)


    def enable_qr_detection(self, enabled: bool):
        ''' Activer/désactiver la détection QR '''
        self.qr_enabled = enabled
        if self.qr_enabled and self.qr_detector is None:
            try:
                self.qr_detector = cv2.QRCodeDetector()
            except Exception as e:
                logger.info(f"[PICAM][QR] Impossible d'initialiser QR detector: {e}")
                self.qr_detector = None
                self.qr_enabled = False
        elif not self.qr_enabled:
            self.qr_detector = None
          

    def start(self):
        if self.is_running:
            return True
        if self.picam2 is None:
            logger.info(f"[PICAM] start() impossible: {self.error}")
            return False
        try:
            self.picam2.start()
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            logger.info("[PICAM] Picamera2 démarrée")
            return True
        except Exception as e:
            self.error = f"Failed to start Picamera2: {e}"
            logger.error(f"[PICAM] Erreur lors du démarrage Picamera2: {e}")
            return False

    def _capture_loop(self):
        period = 1.0 / max(1, self.framerate)
        consecutive_errors = 0
        max_errors = 10
        while self.is_running:
            try:
                arr = self.picam2.capture_array()
                if arr is None:
                    consecutive_errors += 1
                    logger.info(f"[PICAM] capture_array renvoyé None (tentative {consecutive_errors}/{max_errors})")
                    if consecutive_errors >= max_errors:
                        logger.info("[PICAM] trop d'erreurs, arrêt capture")
                        self.is_running = False
                    time.sleep(0.1)
                    continue
                consecutive_errors = 0

                # conversion RGB -> BGR pour OpenCV
                try:
                    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                except Exception:
                    bgr = arr

                # Détection QR (optionnelle, cadencée et redimensionnée)
                if self.qr_enabled and self.qr_detector is not None:
                    self._frame_count += 1
                    if (self._frame_count % self.detect_every_n_frames) == 0:
                        try:
                            h, w = arr.shape[:2]
                            scale = 1.0
                            if w > self.detect_downscale_width:
                                scale = float(self.detect_downscale_width) / float(w)
                                new_w = int(w * scale)
                                new_h = int(h * scale)
                                small = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                                small_w = new_w
                            else:
                                small = arr
                                small_w = w
                            # detectAndDecode accepte BGR ou gray
                            data, points, _ = self.qr_detector.detectAndDecode(small)
                            if data:
                                now = time.time()
                                # éviter répétitions trop fréquentes
                                if data != self._last_qr or (now - self._last_qr_ts) > self.qr_debounce_seconds:
                                    self._last_qr = data
                                    self._last_qr_ts = now
                                    logger.info(f"[PICAM][QR] QR détecté: {data}")
                                    if callable(self.qr_callback):
                                        # Remapper les points vers la taille originale si nécessaire
                                        pts_copy = None
                                        if points is not None:
                                            try:
                                                pts_arr = points.reshape(-1, 2)
                                                # remap : coord_orig = coord_small * (orig_width / small_width)
                                                inv_scale = float(w) / float(small_w) if small_w != 0 else 1.0
                                                orig_corners = [(int(x * inv_scale), int(y * inv_scale)) for x, y in pts_arr]
                                                pts_copy = orig_corners
                                            except Exception:
                                                pts_copy = None
                                        threading.Thread(target=self.qr_callback, args=(data, pts_copy), daemon=True).start()
                        except Exception as e:
                            logger.info(f"[PICAM][QR] Erreur détection QR: {e}")

                # encoder en JPEG
                try:
                    ret, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret and jpeg is not None:
                        with self.lock:
                            self.frame = jpeg.tobytes()
                except Exception as e:
                    logger.info(f"[PICAM] Erreur encodage JPEG: {e}")

                time.sleep(period)
            except Exception as e:
                consecutive_errors += 1
                logger.info(f"[PICAM] Erreur capture Picamera2: {e} (tentative {consecutive_errors}/{max_errors})")
                if consecutive_errors >= max_errors:
                    logger.info("[PICAM] trop d'erreurs, arrêt capture")
                    self.is_running = False
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.frame

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        try:
            if self.picam2 is not None:
                self.picam2.stop()
                logger.info("[PICAM] Picamera2 arrêtée")
        except Exception as e:
            logger.info(f"[PICAM] Erreur lors de l'arrêt Picamera2: {e}")


class MockCamera:
    """
    Simulate a camera for development.
    - If video_path provided, reads frames in loop from that file.
    - If images_dir provided, cycles through images.
    - Otherwise generates a test pattern with timestamp.
    API:
      cam = MockCamera(video_path="...")  # or images_dir="/path"
      ret, frame = cam.read()
      cam.release()
    """

    def __init__(self, video_path: Optional[str] = None, images_dir: Optional[str] = None,
                 width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self._video = None
        self._images = []
        self._idx = 0
        if video_path:
            self._video = cv2.VideoCapture(video_path)
            self._video.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._video.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if images_dir:
            import os
            exts = (".jpg", ".jpeg", ".png", ".bmp")
            self._images = sorted([os.path.join(images_dir, f) for f in os.listdir(images_dir)
                                   if f.lower().endswith(exts)])
        self._last_time = time.time()
    
    def start(self):
        return True
    
    def _read_frame(self) -> Optional[np.ndarray]:
        # Maintain target FPS
        now = time.time()
        wait = max(0, (1.0 / self.fps) - (now - self._last_time))
        if wait > 0:
            time.sleep(wait)
        self._last_time = time.time()

        if self._video is not None and self._video.isOpened():
            ret, frame = self._video.read()
            if not ret or frame is None:
                # loop video
                self._video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._video.read()
                if not ret or frame is None:
                    return None
            frame = cv2.resize(frame, (self.width, self.height))
            return frame

        if len(self._images) > 0:
            path = self._images[self._idx % len(self._images)]
            frame = cv2.imread(path)
            if frame is None:
                return None
            frame = cv2.resize(frame, (self.width, self.height))
            self._idx += 1
            return frame

        # Generate test pattern with timestamp
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"MockCam {t}", (30, int(self.height/2)), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0,255,0), 2, cv2.LINE_AA)
        # moving circle
        x = int((time.time() * 100) % self.width)
        cv2.circle(frame, (x, int(self.height*0.75)), 30, (0,128,255), -1)
        return frame

    # Helper pour s'assurer d'avoir des bytes JPEG
    def _to_jpeg_bytes(self, frame):
        if frame is None:
            return None
        if isinstance(frame, (bytes, bytearray)):
            return bytes(frame)
        try:
            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ret or jpeg is None:
                return None
            return jpeg.tobytes()
        except Exception as e:
            logger.info(f"[CAMERA] Erreur encodage frame: {e}")
            return None

    def get_frame(self):
        frame = self._read_frame()
        if frame is None:       
            return None
        return self._to_jpeg_bytes(frame)

    def stop(self):
        if self._video is not None and self._video.isOpened():
            self._video.release()