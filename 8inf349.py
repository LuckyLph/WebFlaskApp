from flask import Flask, request, jsonify, make_response
from flask import g
from flask import redirect
from flask import session
from flask import url_for, abort, render_template, flash
from flask.cli import with_appcontext
from functools import wraps
from hashlib import md5
from peewee import *
import json
import sqlite3
import requests
import os
import click

DATABASE = 'products.sqlite'
app = Flask(__name__)
database = SqliteDatabase(DATABASE)

class BaseModel(Model):
    class Meta:
        database = database

class Product(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    name = TextField()
    typeOf = TextField()
    description = TextField()
    image = TextField()
    height = IntegerField()
    weight = IntegerField()
    price = FloatField()
    rating = IntegerField()
    inStock = BooleanField()

    def getProductsFromService():
        url = 'http://jgnault.ddns.net/shops/products/'
        json_data = requests.get(url).json()
        for i in json_data['products']:
            product = Product.create(
                id = int(i['id']),
                name = i['name'],
                typeOf = i['type'],
                description = i['description'],
                image = i['image'],
                height = i['height'],
                weight = i['weight'],
                price = i['price'],
                rating = i['rating'],
                inStock = i['in_stock']
        )

class ShippingInformation(BaseModel):
    country = TextField(null = True)
    address = TextField(null = True)
    postalCode = TextField(null = True)
    city = TextField(null = True)
    province = TextField(null = True)

class CreditCard(BaseModel):
    name = TextField(null = True)
    firstDigits = TextField(null = True)
    lastDigits = TextField(null = True)
    expirationYear = TextField(null = True)
    expirationMonth = TextField(null = True)

class Transaction(BaseModel):
    id = TextField(primary_key=True, unique=True)
    success = BooleanField(null = True)
    amountCharged = FloatField(null = True)

class Order(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    shippingInformation = ForeignKeyField(ShippingInformation, null = True)
    product = ForeignKeyField(Product, null = True)
    creditCard = ForeignKeyField(CreditCard, null = True)
    transaction = ForeignKeyField(Transaction, null = True)
    email = TextField(null = True)
    totalPrice = FloatField()
    paid = BooleanField()
    shippingPrice = FloatField()
    quantity = IntegerField()

def db_connection():
    conn = None
    try:
        conn = sqlite3.connect("products.sqlite")
    except sqlite3.Error as e:
        print(e)
    return conn

# simple utility function to create tables
def create_tables():
    with database:
        database.create_tables([Product, ShippingInformation, CreditCard, Transaction, Order])

@app.route('/', methods=['GET'])
def products():  
    conn = db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if request.method == 'GET':
        rows = cursor.execute("SELECT * FROM product").fetchall()
        conn.commit()
        conn.close()
    response = [dict(ix) for ix in rows]
    res = make_response(jsonify({"products" : response}), 200)
    return res, 200
     

@app.route('/order', methods=['POST'])
def create_order():
    if request.is_json:
        req = request.get_json()
        product_received = req.get("product")
        if product_received is None:
            return make_response(jsonify({"errors" : {"product": {"code" : "missing-fields", "name" : "La création d'une commande nécessite un produit"}}})), 422
        id_received = product_received.get("id")
        quantity_received = product_received.get("quantity")
        if id_received is None or quantity_received is None:
            return make_response(jsonify({"errors" : {"product": {"code" : "missing-fields", "name" : "La création d'une commande nécessite un produit"}}})), 422
        conn = db_connection()
        cursor = conn.cursor()
        product = None
        if request.method == 'POST':
            cursor.execute("SELECT * FROM product WHERE id=?", (id_received,))
            rows = cursor.fetchall()
            for r in rows:
                product = r
            if product is not None:
                if product[9] == False:
                    return make_response(jsonify({"errors" : {"product": {"code" : "out-of-inventory", "name" : "Le produit demandé n'est pas en inventaire"}}})), 422
                new_total_price = product[7] * quantity_received
                if product[6] * quantity_received < 500:
                    new_shipping_price = 5
                elif product[6] * quantity_received < 2000:
                    new_shipping_price = 10
                elif product[6] * quantity_received >= 2000:
                    new_shipping_price = 25
                
                shippingInformation = ShippingInformation()
                creditCard = CreditCard()
                transaction = Transaction()
                product_ = Product()
                
                product_, created = Product.get_or_create(id = id_received)
                shippingInformation, created = ShippingInformation.get_or_create(defaults={'country': None, 'address': None, 'postalCode': None, 'city': None, 'province': None})
                creditCard, created = CreditCard.get_or_create(defaults={'name': None, 'firstDigits': None, 'lastDigits': None, 'expirationYear': None, 'expirationMonth': None})
                transaction, created = Transaction.get_or_create(id = id, defaults={'success': None, 'amountCharged': None})
                
                sql = """INSERT INTO "order" (shippingInformation_id, product_id, creditCard_id, transaction_id, email, totalPrice, paid, shippingPrice, quantity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                cursor = cursor.execute(sql, (None, id_received, None, None, None, new_total_price, False, new_shipping_price, quantity_received))
                conn.commit()
                conn.close()
                return "Location: /order/<int:order_id>", 302
            else:
                return "Something wrong", 422
        else:
            return "Bad request method", 400
    else:
        return "No JSON received", 400
    

@app.route('/order/<int:id>', methods=['GET', 'PUT'])
def get_order(id):
    conn = db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    order = None
    if request.method == 'GET':
        cursor.execute("""SELECT * FROM "order" WHERE id=?""", (id,))
        rows = cursor.fetchall()
        if rows is not None:
            conn.commit()
            conn.close()
            response = [dict(ix) for ix in rows]
            res = make_response(jsonify({"order" : response}), 200)
            return res, 200  
        else:
            return "Commande non existante", 404
            
    if request.method == 'PUT':
        cursor.execute("""SELECT * FROM "order" WHERE id=?""", (id,))
        rows = cursor.fetchall()
        order = None
        for r in rows:
            order = r
        if order is not None:        
            if order[5] == None and order[1] == None:           
                req = request.get_json()
                if req.get("credit_card") is not None:
                    return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Les information du client sont nécessaire avant d'appliquer une carte de crédit"}}})), 422
                order_received = req.get("order")
                if order_received is None:
                    return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque1 un ou plusieurs champs qui sont obligatoires"}}})), 422
                email_received = order_received.get("email")
                shipping_information_received = order_received.get("shipping_information")
                if email_received is None or shipping_information_received is None:
                    return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque2 un ou plusieurs champs qui sont obligatoires"}}})), 422
                country_received = shipping_information_received.get("country")
                address_received = shipping_information_received.get("address")
                postal_code_received = shipping_information_received.get("postal_code")
                city_received = shipping_information_received.get("city")
                province_received = shipping_information_received.get("province")
                if country_received is None or address_received is None or postal_code_received is None or city_received is None or province_received is None:
                    return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque12 un ou plusieurs champs qui sont obligatoires"}}})), 422
                    
                sql = """ UPDATE "order" 
                        SET email = ?,
                            shippingInformation_id = ?
                        WHERE id=? """
                        
                conn.execute(sql, (email_received, id, id))
                conn.commit()

                sql2 = """ UPDATE "shippinginformation" 
                        SET country = ?,
                            address = ?,
                            postalCode = ?,
                            city = ?,
                            province = ?
                        WHERE id=? """
                
                conn.execute(sql2, (country_received, address_received, postal_code_received, city_received, province_received, id))
                conn.commit()

                cursor.execute("""SELECT * FROM "order" WHERE id=?""", (id,))
                rows2 = cursor.fetchall()
                conn.commit()
                cursor.execute("""SELECT * FROM "shippinginformation" WHERE id=?""", (id,))
                rows3 = cursor.fetchall()
                conn.commit()
                conn.close()
                response = [dict(ix) for ix in rows2]
                response2 = [dict(ix) for ix in rows3]
                res = make_response(jsonify({"order" : response, "shippingInformation" : response2}), 200)
                return res, 200         
            
            elif order[3] is None:          
                req = request.get_json()
                credit_card_received = req.get("credit_card")
                if credit_card_received is None:
                    return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque4 un ou plusieurs champs qui sont obligatoires"}}})), 422
                if order[7] == True:
                    return make_response(jsonify({"errors" : {"order": {"code" : "already-paid", "name" : "La commande a déjà été payée."}}})), 422
                name_received = credit_card_received.get("name")
                number_received = credit_card_received.get("number")
                first_digits_received = number_received[:4]
                last_digits_received = number_received[-4:]
                cvv_received = credit_card_received.get("cvv")
                expiration_year_received = credit_card_received.get("expiration_year")
                expiration_month_received = credit_card_received.get("expiration_month")
                if name_received is None or number_received is None or expiration_year_received is None or expiration_month_received is None or cvv_received is None:
                    return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque5 un ou plusieurs champs qui sont obligatoires"}}})), 422                        
                
                sql = """ UPDATE "order" 
                        SET creditCard_id = ?                            
                        WHERE id=? """
                
                conn.execute(sql, (id, id))
                conn.commit()
                
                sql2 = """ UPDATE "creditcard" 
                        SET name = ?,
                            firstDigits = ?,
                            lastDigits = ?,
                            expirationYear = ?,
                            expirationMonth = ?
                        WHERE id=? """
                
                conn.execute(sql2, (name_received, first_digits_received, last_digits_received, expiration_year_received, expiration_month_received, id))
                conn.commit()
                
                cursor.execute("""SELECT * FROM "order" WHERE id=?""", (id,))
                rows2 = cursor.fetchall()
                order2 = None
                for r in rows2:
                    order2 = r
                conn.commit()
                cursor.execute("""SELECT * FROM "shippinginformation" WHERE id=?""", (id,))
                rows3 = cursor.fetchall()
                conn.commit()
                cursor.execute("""SELECT * FROM "creditcard" WHERE id=?""", (id,))
                rows4 = cursor.fetchall()
                conn.commit()
                
                json_to_send = {
                    "credit_card" : {
                        "name" : name_received,
                        "number" : number_received,
                        "expiration_year" : expiration_year_received,
                        "cvv" : cvv_received,
                        "expiration_month" : expiration_month_received
                    },
                    "amount_charged" : order2[6] + order2[8]
                }
                
                url = 'http://jgnault.ddns.net/shops/pay/'
                json_data = requests.post(url, data=json.dumps(json_to_send)).json()
                
                if json_data.get("errors") is not None:
                    return make_response(json_data['transaction']), 422
                
                transaction_received = json_data.get("transaction")
                id_received = transaction_received.get("id")
                success_received = transaction_received.get("success")
                amount_charged_received = transaction_received.get("amount_charged")
                
                sql3 = """ UPDATE "transaction" 
                        SET id = ?,
                            success = ?,
                            amountCharged = ?
                        WHERE id=? """
                
                conn.execute(sql3, (id_received, success_received, amount_charged_received, "<built-in function id>"))
                conn.commit()
                
                cursor.execute("""SELECT * FROM "transaction" WHERE id=?""", (id_received,))
                rows5 = cursor.fetchall()
                conn.commit()           
                conn.close()
                
                response = [dict(ix) for ix in rows2]
                response2 = [dict(ix) for ix in rows3]
                response3 = [dict(ix) for ix in rows4]
                response4 = [dict(ix) for ix in rows5]
                res = make_response(jsonify({"order" : response, "shippingInformation" : response2, "creditCard" : response3, "transaction" : response4}), 200)
                return res, 200  
        else:
            return "Commande non existante", 404    

def initialize():
    app.cli.add_command(init_db_command)
    Product.getProductsFromService()


if __name__ == '__main__':
    initialize()
    app.run()

@app.cli.command("init-db")
def init_db_command():
    database = SqliteDatabase(DATABASE)
    if os.path.exists("products.sqlite"):
        os.remove("products.sqlite")
    create_tables()
    click.echo("Initialized the database.")