from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = sqlite3.connect(os.path.join(base_dir, "db.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio REAL, stock INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, lugar TEXT, producto TEXT, cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime')))")
    db.execute("CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, direccion TEXT, detalle TEXT, total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime')))")
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    db = get_db()
    productos = db.execute("SELECT * FROM productos").fetchall()
    db.close()
    return render_template("index.html", productos=productos)

@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT id, nombre, precio, stock FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])

@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock) VALUES (?, ?, ?)", 
               (request.form["nombre"], float(request.form["precio"]), int(request.form["stock"])))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/eliminar_producto/<int:id>")
def eliminar_producto(id):
    db = get_db()
    db.execute("DELETE FROM productos WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    prod_nom = request.form["producto"]
    cant = int(request.form["cantidad"])
    db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?, ?, ?, ?)", 
               (request.form["lugar"], prod_nom, cant, float(request.form["total"])))
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (cant, prod_nom))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = json.loads(request.form["data"])
    total_venta = 0
    detalle_lista = []
    for item in data["carrito"]:
        p = db.execute("SELECT * FROM productos WHERE id=?", (item["id"],)).fetchone()
        if p:
            sub = p["precio"] * item["cantidad"]
            total_venta += sub
            detalle_lista.append({"nombre": p["nombre"], "cantidad": item["cantidad"], "precio": p["precio"], "subtotal": sub})
            db.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
    
    pagado = float(data.get("pagado") or 0)
    saldo = max(0, total_venta - pagado)
    estado = "pagado" if saldo <= 0 else ("parcial" if pagado > 0 else "fiado")
    
    db.execute("INSERT INTO ventas (cliente, direccion, detalle, total, pagado, saldo, estado) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (data["cliente"]["nombre"], data["cliente"]["direccion"], json.dumps(detalle_lista), total_venta, pagado, saldo, estado))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/pagar_boleta/<int:id>", methods=["POST"])
def pagar_boleta(id):
    db = get_db()
    monto = float(request.form.get("monto", 0))
    venta = db.execute("SELECT total, pagado FROM ventas WHERE id=?", (id,)).fetchone()
    if venta:
        n_pagado = venta["pagado"] + monto
        n_saldo = max(0, venta["total"] - n_pagado)
        estado = "pagado" if n_saldo <= 0 else "parcial"
        db.execute("UPDATE ventas SET pagado=?, saldo=?, estado=? WHERE id=?", (n_pagado, n_saldo, estado, id))
        db.commit()
    db.close()
    return redirect("/boletas")

@app.route("/eliminar_venta/<int:id>")
def eliminar_venta(id):
    db = get_db()
    venta = db.execute("SELECT detalle FROM ventas WHERE id=?", (id,)).fetchone()
    if venta:
        for item in json.loads(venta["detalle"]):
            db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (item["cantidad"], item["nombre"]))
    db.execute("DELETE FROM ventas WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect("/boletas")

@app.route("/clientes")
def clientes():
    db = get_db()
    query = """
        SELECT cliente, direccion, SUM(total) as total_gastado, COUNT(id) as total_compras,
        ROUND(AVG(total), 2) as promedio_compra,
        (SELECT json_extract(detalle, '$[0].nombre') FROM ventas v2 WHERE v2.cliente = ventas.cliente 
         GROUP BY json_extract(detalle, '$[0].nombre') ORDER BY COUNT(*) DESC LIMIT 1) as producto_top
        FROM ventas GROUP BY cliente ORDER BY total_gastado DESC
    """
    res = db.execute(query).fetchall()
    db.close()
    return render_template("clientes.html", clientes=res)

@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
