"""
Sistema de Fiscalizacao de EPIs - Flask App
"""

from flask import (
    Flask, render_template, redirect, url_for,
    session, request, jsonify, Response, flash
)
from functools import wraps
from database.db import DatabaseManager
import detector as det_module
from detector import CameraStream
import threading

app = Flask(__name__)
app.secret_key = "epi_sistema_2024_seguro"

db = DatabaseManager()
cameras = {}
cameras_lock = threading.Lock()


def login_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.route("/")
def raiz():
    return redirect(url_for("monitoramento") if "usuario_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        if not usuario or not senha:
            erro = "Preencha usuario e senha."
        else:
            user = db.validar_usuario(usuario, senha)
            if user:
                session["usuario_id"] = user["id"]
                session["usuario_nome"] = user["nome"]
                return redirect(url_for("monitoramento"))
            else:
                erro = "Usuario ou senha invalidos."
    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── MONITORAMENTO ───────────────────────────────────────────────────────────

@app.route("/monitoramento")
@login_obrigatorio
def monitoramento():
    return render_template("monitoramento.html",
                           usuario=session.get("usuario_nome"),
                           flash_habilitado=det_module.FLASH_HABILITADO,
                           epis_monitorados=list(det_module.EPIS_MONITORADOS))


@app.route("/stream/<camera_id>")
@login_obrigatorio
def stream(camera_id):
    with cameras_lock:
        if camera_id not in cameras:
            cam = CameraStream(camera_source=det_module.CAMERA_SOURCE, camera_id=camera_id)
            cam.iniciar()
            cameras[camera_id] = cam

    def gerar():
        cam = cameras[camera_id]
        while True:
            frame = cam.obter_frame_jpeg()
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    return Response(gerar(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ─── API ─────────────────────────────────────────────────────────────────────

@app.route("/api/flash", methods=["POST"])
@login_obrigatorio
def api_flash():
    """Liga ou desliga o flash do celular."""
    acao = request.json.get("acao", "toggle")
    if acao == "on":
        det_module.FLASH_HABILITADO = True
        det_module.ligar_flash()
    elif acao == "off":
        det_module.FLASH_HABILITADO = False
        det_module.desligar_flash()
    else:
        det_module.FLASH_HABILITADO = not det_module.FLASH_HABILITADO
        if not det_module.FLASH_HABILITADO:
            det_module.desligar_flash()
    return jsonify({"flash": det_module.FLASH_HABILITADO})


@app.route("/api/estatisticas")
@login_obrigatorio
def api_estatisticas():
    return jsonify(db.estatisticas())


@app.route("/api/ocorrencias")
@login_obrigatorio
def api_ocorrencias():
    return jsonify(db.listar_ocorrencias(limite=15))


@app.route("/api/limpar", methods=["POST"])
@login_obrigatorio
def api_limpar():
    db.limpar_ocorrencias()
    return jsonify({"ok": True})


# ─── DADOS ───────────────────────────────────────────────────────────────────

@app.route("/dados")
@login_obrigatorio
def dados():
    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = 12
    offset = (pagina - 1) * por_pagina

    filtros = {
        "camera_id": request.args.get("camera") or None,
        "data_inicio": request.args.get("data_inicio") or None,
        "data_fim": request.args.get("data_fim") or None,
        "epi_filtro": request.args.get("epi") or None,
    }

    ocorrencias = db.listar_ocorrencias(limite=por_pagina, offset=offset, **filtros)
    total = db.contar_ocorrencias(**filtros)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    return render_template("dados.html",
                           ocorrencias=ocorrencias,
                           pagina=pagina,
                           total_paginas=total_paginas,
                           total=total,
                           filtros=filtros,
                           usuario=session.get("usuario_nome"))


@app.route("/dados/<int:oid>")
@login_obrigatorio
def detalhe(oid):
    ocorrencia = db.obter_ocorrencia(oid)
    if not ocorrencia:
        flash("Ocorrencia nao encontrada.", "erro")
        return redirect(url_for("dados"))
    return render_template("detalhe.html", ocorrencia=ocorrencia,
                           usuario=session.get("usuario_nome"))


if __name__ == "__main__":
    print("=" * 55)
    print("  Sistema EPI | http://localhost:5000")
    print("  Login: admin / admin123")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
