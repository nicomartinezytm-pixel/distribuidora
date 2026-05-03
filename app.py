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
    db.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT NOT NULL, precio REAL NOT NULL, stock INTEGER NOT NULL, 
            unidad TEXT DEFAULT 'Unidad', oferta TEXT DEFAULT ''
        )""")
    db.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            lugar TEXT, direccion TEXT, producto TEXT, 
            cantidad INTEGER, total REAL, fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            cliente TEXT, direccion TEXT, telefono TEXT, detalle TEXT, 
            total REAL, pagado REAL DEFAULT 0, saldo REAL DEFAULT 0, 
            estado TEXT DEFAULT 'fiado', fecha TEXT DEFAULT (DATETIME('now','localtime'))
        )""")
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM productos ORDER BY nombre ASC").fetchall()
    productos = [dict(r) for r in rows]
    db.close()
    return render_template("index.html", productos=productos)

# --- SISTEMA DE VENTAS ---
@app.route("/vender")
def vender():
    return render_template("ventas.html")

@app.route("/productos_json")
def productos_json():
    db = get_db()
    productos = db.execute("SELECT id, nombre, precio, stock, unidad, oferta FROM productos").fetchall()
    db.close()
    return jsonify([dict(p) for p in productos])

@app.route("/finalizar_venta", methods=["POST"])
def finalizar_venta():
    try:
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
        
        # Insertamos la venta con pagado=0 y saldo=total inicial
        db.execute("""INSERT INTO ventas (cliente, direccion, telefono, detalle, total, pagado, saldo, estado) 
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                   (data["cliente"]["nombre"], data["cliente"]["direccion"], data["cliente"]["telefono"], 
                    json.dumps(detalle_lista), total_venta, 0, total_venta, "fiado"))
        db.commit()
        db.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- COBRANZAS (Aquí estaba el error) ---
@app.route("/boletas")
def boletas():
    db = get_db()
    res = db.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    db.close()
    return render_template("boletas.html", boletas=res)

@app.route("/registrar_pago", methods=["POST"])
def registrar_pago():
    try:
        db = get_db()
        id_venta = request.form.get('id')
        monto_nuevo_pago = float(request.form.get('monto', 0))
        
        venta = db.execute("SELECT total, pagado FROM ventas WHERE id = ?", (id_venta,)).fetchone()
        
        if venta:
            nuevo_total_pagado = venta['pagado'] + monto_nuevo_pago
            nuevo_saldo = venta['total'] - nuevo_total_pagado
            
            # Ajuste de estado
            if nuevo_saldo <= 0:
                estado = "pagado"
                nuevo_saldo = 0
            elif nuevo_total_pagado > 0:
                estado = "parcial"
            else:
                estado = "fiado"

            db.execute("UPDATE ventas SET pagado=?, saldo=?, estado=? WHERE id=?", 
                       (nuevo_total_pagado, nuevo_saldo, estado, id_venta))
            db.commit()
        db.close()
        return redirect("/boletas")
    except Exception as e:
        return f"Error al cobrar: {e}", 500

# --- PRODUCTOS (Agregar, Editar, Eliminar) ---
@app.route("/agregar_producto", methods=["POST"])
def agregar_producto():
    db = get_db()
    db.execute("INSERT INTO productos (nombre, precio, stock, unidad, oferta) VALUES (?, ?, ?, ?, ?)", 
               (request.form['nombre'], float(request.form['precio']), int(request.form['stock']), 
                request.form.get('unidad', 'Unidad'), request.form.get('oferta', '')))
    db.commit()
    db.close()
    return redirect("/")

@app.route("/editar_producto", methods=["POST"])
def editar_producto():
    db = get_db()
    db.execute("UPDATE productos SET nombre=?, precio=?, stock=?, unidad=?, oferta=? WHERE id=?",
               (request.form['nombre'], float(request.form['precio']), int(request.form['stock']), 
                request.form['unidad'], request.form['oferta'], int(request.form['id'])))
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

# --- COMPRAS ---
@app.route("/compras")
def compras():
    db = get_db()
    historial = db.execute("SELECT * FROM compras ORDER BY id DESC").fetchall()
    productos = db.execute("SELECT nombre, stock FROM productos ORDER BY nombre ASC").fetchall()
    db.close()
    return render_template("compras.html", historial=historial, productos=productos)

@app.route("/agregar_compra", methods=["POST"])
def agregar_compra():
    db = get_db()
    db.execute("INSERT INTO compras (lugar, direccion, producto, cantidad, total) VALUES (?, ?, ?, ?, ?)",
               (request.form['lugar'], request.form['direccion'], request.form['producto'], 
                int(request.form['cantidad']), float(request.form['total'])))
    db.execute("UPDATE productos SET stock = stock + ? WHERE nombre = ?", 
               (int(request.form['cantidad']), request.form['producto']))
    db.commit()
    db.close()
    return redirect("/compras")

@app.route("/clientes")
def clientes():
    db = get_db()
    res = db.execute("""SELECT cliente, direccion, telefono, SUM(total) as total_gastado, 
                        SUM(saldo) as deuda_total, COUNT(id) as total_compras 
                        FROM ventas GROUP BY cliente ORDER BY deuda_total DESC""").fetchall()
    db.close()
    return render_template("clientes.html", clientes=res)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
