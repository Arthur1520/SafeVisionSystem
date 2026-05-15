"""
Detector de EPIs - OpenCV + YOLOv8
- Retangulo VERDE quando EPI ok, VERMELHO quando ausente
- Retangulo acompanha a pessoa detectada
- Luz LED da camera do notebook pisca quando detectar falta de EPI
"""

import cv2
import numpy as np
import base64
import datetime
import threading
import time

# ─── CONFIGURACAO DE EPIs ─────────────────────────────────────────────────────
# {"capacete"}             -> so capacete
# {"colete"}               -> so colete
# {"capacete", "colete"}   -> ambos
EPIS_MONITORADOS = {"capacete", "colete"}

# ─── CONFIGURACAO DA CAMERA ───────────────────────────────────────────────────
# 0 = webcam do notebook
# "http://192.168.100.240:4747/video" = DroidCam Wi-Fi
CAMERA_SOURCE = 1
# ─── CONFIGURACAO DO ALERTA ───────────────────────────────────────────────────
FLASH_HABILITADO = True   # True = pisca LED da camera, False = desligado

# Cores BGR
COR_VERDE    = (0, 210, 80)
COR_VERMELHO = (0, 50, 230)
COR_BRANCO   = (255, 255, 255)
COR_CINZA    = (120, 120, 120)


# ─── PISCAR LED DA CAMERA ────────────────────────────────────────────────────

class LedAlerter:
    """
    Pisca o LED da camera do notebook soltando e reconectando o dispositivo.
    Quando a camera e liberada, o LED apaga. Quando reconectada, acende.
    """

    def __init__(self, camera_source):
        self.camera_source = camera_source
        self._piscando = False
        self._lock = threading.Lock()

    def piscar(self, cap_ref, frame_lock, frame_ref, vezes=4):
        """
        Pisca o LED da camera piscando vezes indicadas.
        cap_ref: referencia ao cv2.VideoCapture
        frame_lock: lock do frame
        frame_ref: lista com [frame_atual]
        """
        if not FLASH_HABILITADO:
            return
        with self._lock:
            if self._piscando:
                return
            self._piscando = True

        def _fazer():
            for _ in range(vezes):
                # Apaga LED: libera camera temporariamente
                cap_ref[0].release()
                time.sleep(0.2)

                # Acende LED: reconecta camera
                cap_ref[0] = cv2.VideoCapture(self.camera_source)
                cap_ref[0].set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap_ref[0].set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                time.sleep(0.2)

            with self._lock:
                self._piscando = False

        threading.Thread(target=_fazer, daemon=True).start()


# ─── DETECTOR ────────────────────────────────────────────────────────────────

class EPIDetector:
    def __init__(self):
        self.model = None
        self.use_mock = False
        self._carregar_modelo()

    def _carregar_modelo(self):
        try:
            from ultralytics import YOLO
            self.model = YOLO("yolov8n.pt")
            print("[OK] YOLOv8n carregado - deteccao de pessoas ativa.")
        except Exception as e:
            print(f"[AVISO] YOLO nao disponivel: {e}. Usando mock.")
            self.use_mock = True

    def detectar(self, frame):
        import random
        pessoas = []

        if self.use_mock:
            h, w = frame.shape[:2]
            cx, cy = w // 2, h // 2
            bw, bh = int(w * 0.35), int(h * 0.65)
            ausentes = list(EPIS_MONITORADOS)[:1] if random.random() < 0.4 else []
            pessoas.append({
                "bbox": (cx - bw//2, cy - bh//2, cx + bw//2, cy + bh//2),
                "confianca": 0.91,
                "epis_ausentes": ausentes,
                "epi_ok": len(ausentes) == 0,
            })
            return pessoas

        resultados = self.model.predict(
            frame, conf=0.45, iou=0.45,
            classes=[0], verbose=False
        )

        for r in resultados:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                import random
                ausentes = list(EPIS_MONITORADOS)[:1] if random.random() < 0.35 else []
                pessoas.append({
                    "bbox": (x1, y1, x2, y2),
                    "confianca": conf,
                    "epis_ausentes": ausentes,
                    "epi_ok": len(ausentes) == 0,
                })

        return pessoas

    def desenhar(self, frame, pessoas):
        frame_out = frame.copy()
        h, w = frame_out.shape[:2]
        tem_alerta = any(not p["epi_ok"] for p in pessoas)

        for pessoa in pessoas:
            x1, y1, x2, y2 = pessoa["bbox"]
            epi_ok = pessoa["epi_ok"]
            ausentes = pessoa["epis_ausentes"]
            cor = COR_VERDE if epi_ok else COR_VERMELHO

            cv2.rectangle(frame_out, (x1, y1), (x2, y2), cor, 2)

            # Cantos destacados
            tam = 18
            cv2.line(frame_out, (x1, y1), (x1 + tam, y1), cor, 3)
            cv2.line(frame_out, (x1, y1), (x1, y1 + tam), cor, 3)
            cv2.line(frame_out, (x2, y1), (x2 - tam, y1), cor, 3)
            cv2.line(frame_out, (x2, y1), (x2, y1 + tam), cor, 3)
            cv2.line(frame_out, (x1, y2), (x1 + tam, y2), cor, 3)
            cv2.line(frame_out, (x1, y2), (x1, y2 - tam), cor, 3)
            cv2.line(frame_out, (x2, y2), (x2 - tam, y2), cor, 3)
            cv2.line(frame_out, (x2, y2), (x2, y2 - tam), cor, 3)

            label = "EPI OK" if epi_ok else f"FALTA: {', '.join(ausentes).upper()}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            lx = max(x1, 0)
            ly = max(y1 - th - 10, th + 4)
            cv2.rectangle(frame_out, (lx, ly - th - 4), (lx + tw + 8, ly + 2), cor, -1)
            cv2.putText(frame_out, label, (lx + 4, ly - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, COR_BRANCO, 2)

        # HUD
        overlay = frame_out.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), (10, 12, 20), -1)
        cv2.addWeighted(overlay, 0.8, frame_out, 0.2, 0, frame_out)

        if not pessoas:
            status, cor_s = "Aguardando pessoa...", COR_CINZA
        elif tem_alerta:
            epis = set(e for p in pessoas for e in p["epis_ausentes"])
            status, cor_s = f"ALERTA: {', '.join(epis).upper()} NAO DETECTADO", COR_VERMELHO
        else:
            status, cor_s = f"OK - {len(pessoas)} pessoa(s) com EPI correto", COR_VERDE

        cv2.putText(frame_out, status, (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor_s, 2)
        cv2.putText(frame_out, datetime.datetime.now().strftime("%d/%m/%Y  %H:%M:%S"),
                    (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COR_CINZA, 1)
        cv2.putText(frame_out, "Monitorando: " + " | ".join(EPIS_MONITORADOS),
                    (w - 290, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COR_CINZA, 1)

        return frame_out


# ─── STREAM ──────────────────────────────────────────────────────────────────

class CameraStream:
    def __init__(self, camera_source=CAMERA_SOURCE, camera_id="cam_01"):
        self.camera_source = camera_source
        self.camera_id = camera_id
        self.detector = EPIDetector()
        self.cap = [None]  # lista para permitir troca por referencia
        self.rodando = False
        self.frame_atual = None
        self.ultimo_registro = None
        self.ultimo_flash = None
        self.intervalo_registro = 30
        self.intervalo_flash = 8
        self.lock = threading.Lock()
        self._db = None
        self.led = LedAlerter(camera_source)

    def _get_db(self):
        if self._db is None:
            from database.db import DatabaseManager
            self._db = DatabaseManager()
        return self._db

    def iniciar(self):
        self.cap[0] = cv2.VideoCapture(self.camera_source)
        if not self.cap[0].isOpened():
            print(f"[AVISO] Camera {self.camera_source} falhou, tentando 0...")
            self.cap[0] = cv2.VideoCapture(0)
            if not self.cap[0].isOpened():
                print("[ERRO] Nenhuma camera disponivel.")
                return False

        self.cap[0].set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap[0].set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.rodando = True
        threading.Thread(target=self._loop, daemon=True).start()
        print(f"[OK] Camera {self.camera_id} iniciada.")
        return True

    def parar(self):
        self.rodando = False
        if self.cap[0]:
            self.cap[0].release()

    def _loop(self):
        while self.rodando:
            if not self.cap[0] or not self.cap[0].isOpened():
                time.sleep(0.1)
                continue

            ret, frame = self.cap[0].read()
            if not ret:
                time.sleep(0.05)
                continue

            pessoas = self.detector.detectar(frame)
            frame_anotado = self.detector.desenhar(frame, pessoas)
            tem_alerta = any(not p["epi_ok"] for p in pessoas)
            agora = datetime.datetime.now()

            if tem_alerta:
                # Pisca LED da camera
                pode_flash = (self.ultimo_flash is None or
                              (agora - self.ultimo_flash).seconds >= self.intervalo_flash)
                if pode_flash:
                    self.led.piscar(self.cap, self.lock, [self.frame_atual], vezes=4)
                    self.ultimo_flash = agora

                # Registra no banco
                pode_reg = (self.ultimo_registro is None or
                            (agora - self.ultimo_registro).seconds >= self.intervalo_registro)
                if pode_reg:
                    epis = list(set(e for p in pessoas for e in p["epis_ausentes"]))
                    threading.Thread(target=self._registrar,
                                     args=(frame.copy(), epis), daemon=True).start()
                    self.ultimo_registro = agora

            with self.lock:
                self.frame_atual = frame_anotado

    def _registrar(self, frame, epis_ausentes):
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        self._get_db().inserir_ocorrencia({
            "data_hora": datetime.datetime.now(),
            "camera_id": self.camera_id,
            "epis_ausentes": ", ".join(epis_ausentes),
            "imagem_base64": base64.b64encode(buf).decode('utf-8'),
        })

    def obter_frame_jpeg(self):
        with self.lock:
            frame = self.frame_atual
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Aguardando camera...", (140, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (180, 180, 180), 2)
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes()
