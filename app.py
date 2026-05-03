from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
app.jinja_env.filters['fromjson'] = json.loads

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "db.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    # Aseguramos las 3 tablas base
    db.execute("CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio REAL, stock INTEGER, unidad TEXT, oferta TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, lugar TEXT, producto TEXT, cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime')))")
    db.execute("CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, direccion TEXT, whatsapp TEXT, detalle TEXT, total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime')))")
    
    # Parche por si faltan columnas
    try:
        columnas = [c['name'] for c in db.execute("PRAGMA table_info(ventas)").fetchall()]
        if 'direccion' not in columnas: db.execute("ALTER TABLE ventas ADD COLUMN direccion TEXT")
        if 'whatsapp' not in columnas: db.execute("ALTER TABLE ventas ADD COLUMN whatsapp TEXT")
    except: pass
    
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("index.html", productos=rows)

@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?,?,?,?,?)",
               (request.form['nombre'], float(request.form['precio']), int(request.form['stock']), request.form['unidad'], request.form['oferta']))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    db = get_db()
    v = db.execute("SELECT SUM(total) FROM ventas").fetchone()[0] or 0
    c = db.execute("SELECT SUM(total) FROM compras").fetchone()[0] or 0
    alerta = db.execute("SELECT COUNT(id) FROM productos WHERE stock < 10").fetchone()[0] or 0
    db.close()
    return render_template("dashboard.html", total_ventas=v, total_compras=c, ganancia=v-c, alertas_stock=alerta)

@app.route("/compras")
def compras():
    db = get_db()
    hist = db.execute("SELECT * FROM compras ORDER BY id DESC LIMIT 10").fetchall()
    prods = db.execute("SELECT nombre FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("compras.html", historial=hist, productos=prods)

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    db.execute("INSERT INTO compras (lugar, producto, cantidad, total) VALUES (?,?,?,?)",
               (request.form['lugar'], request.form['producto'], int(request.form['cantidad']), float(request.form['total'])))
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", (int(request.form['cantidad']), request.form['producto']))
    db.commit()
    db.close()
    return redirect("/compras")

@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    db = get_db()
    res = db.execute("SELECT * FROM productos WHERE stock > 0").fetchall()
    db.close()
    return jsonify([dict(r) for r in res])

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    db = get_db()
    data = request.json
    cliente = data["cliente"]
    carrito = data["carrito"]
    total = sum(float(i['precio']) * int(i['cantidad']) for i in carrito)
    db.execute("INSERT INTO ventas (cliente, direccion, whatsapp, detalle, total, saldo) VALUES (?,?,?,?,?,?)",
               (cliente['nombre'], cliente.get('direccion',''), cliente.get('whatsapp',''), json.dumps(carrito), total, total))
    for item in carrito:
        db.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item['cantidad'], item['id']))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/registrar_pago", methods=["POST"])
def registrar_pago():
    db = get_db()
    v = db.execute("SELECT total, pagado FROM ventas WHERE id=?", (request.form['id'],)).fetchone()
    nuevo_pago = v['pagado'] + float(request.form['monto'])
    nuevo_saldo = max(0, v['total'] - nuevo_pago)
    db.execute("UPDATE ventas SET pagado=?, saldo=?, estado=? WHERE id=?", 
               (nuevo_pago, nuevo_saldo, ("pagado" if nuevo_saldo <= 0 else "parcial"), request.form['id']))
    db.commit()
    db.close()
    return redirect("/boletas")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True, threaded=True)
