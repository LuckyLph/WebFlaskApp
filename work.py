from flask import Flask, request, jsonify, make_response
from flask import g
from flask import redirect
from flask import session
from flask import url_for, abort, render_template, flash
from flask import current_app
from flask.cli import with_appcontext
from functools import wraps
from hashlib import md5
from peewee import *
from playhouse.shortcuts import model_to_dict, dict_to_model
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
        
    def __str__(self):
        return self.name

    class Meta:
        tableName = "products"

class ShippingInformation(BaseModel):
    id = IntegerField(primary_key=True, index= True)
    country = TextField(null = True)
    address = TextField(null = True)
    postalCode = TextField(null = True)
    city = TextField(null = True)
    province = TextField(null = True)
    
    def __str__(self):
        return "Shipping to {0}, {1}, {2}, {3}, {4} ".format(self.address, self.postalCode, self.city, self.province, self.country)

    class Meta:
        table_name = "shippingInformations"

class CreditCard(BaseModel):
    id = IntegerField(primary_key=True, index= True)
    name = TextField(null = True)
    firstDigits = TextField(null = True)
    lastDigits = TextField(null = True)
    expirationYear = TextField(null = True)
    expirationMonth = TextField(null = True)
    
    def __str__(self):
        return "Credit card [{0}] owned by '{1}'".format(self.id, self.name)

    class Meta:
        table_name = "creditCards"

class Transaction(BaseModel):
    id = TextField(primary_key=True, unique=True)
    success = BooleanField(null = True)
    amountCharged = FloatField(null = True)
    
    def __str__(self):
        return "Transaction [{0}] of {1}$".format(self.id, self.amountCharged)

    class Meta:
        table_name = "transactions"

class Order(BaseModel):
    id = IntegerField(primary_key=True, unique=True)
    shippingInformation = ForeignKeyField(ShippingInformation, null = True)
    creditCard = ForeignKeyField(CreditCard, null = True)
    transaction = ForeignKeyField(Transaction, null = True)
    email = TextField(null = True)
    totalPrice = FloatField()
    paid = BooleanField(default = False)
    shippingPrice = FloatField()
    
    def __str__(self):
        return "Order [{0}] made by {1}, {2} the total amount of {3}$".format(self.id, self.email, "paid" if self.paid else "didn't pay", self.totalPrice)

    class Meta:
        table_name = "orders"

class OrderProduct(BaseModel):
    order = ForeignKeyField(Order)
    product = ForeignKeyField(Product)
    quantity = IntegerField()

    class Meta:
        table_name = "orderProducts"

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
        database.drop_tables([Product, ShippingInformation, CreditCard, Transaction, Order, OrderProduct])
        database.create_tables([Product, ShippingInformation, CreditCard, Transaction, Order, OrderProduct])
        
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

@app.route('/')
def products():  
    response = list(Product.select().dicts())
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
        if request.method == 'POST':
            try:
                product = Product.get_by_id(product_received["id"])
            except DoesNotExist:
                product = None
            if product != None and product.inStock:
                totalPrice = product.price * product_received["quantity"]
                weight = product.weight * product_received["quantity"]
                if weight * quantity_received < 500:
                    shippingPrice = 5
                elif weight * quantity_received < 2000:
                    shippingPrice = 10
                elif weight * quantity_received >= 2000:
                    shippingPrice = 25             

                order = Order.create(shippingPrice=shippingPrice, totalPrice=totalPrice)
                OrderProduct.create(order=order, product=product, quantity=quantity_received)
               
                return make_response(jsonify({"Location" : "order/{0}".format(order.id) })), 302

            else:
                return make_response(jsonify({"errors" : {"product": {"code" : "out-of-inventory", "name" : "Le produit demandé n'est pas en inventaire"}}})), 422
        else:
            return "Bad request method", 400
    else:
        return "No JSON received", 400   

@app.route('/order/<int:id>', methods=['GET', 'PUT'])
def get_order(id):
    try:
        if (id is None):
            order = None 
        else:
            order = Order.get_by_id(id)
    except DoesNotExist:
        order = None
        
    if(order is None):
        return "Commande non existante", 404
    if request.method == 'GET':  
        order = model_to_dict(order)
        if order["transaction"] == None:
            order["transaction"] = {}
        if order["creditCard"] == None:
            order["creditCard"] = {}
        if order["shippingInformation"] == None:
            order["shippingInformation"] = {}
        orderProduct = OrderProduct.get_by_id(id)
        orderProduct = model_to_dict(orderProduct)
        order["product"] = { "id":orderProduct["id"], "quantity":orderProduct["quantity"]}
        res = make_response(jsonify({"order" : order}), 200)
        return res, 200
            
    if request.method == 'PUT':
        try:
            if (id is None):
                order = None 
            else:
                order = Order.get_by_id(id)
        except DoesNotExist:
            order = None
            
        if(order is None):
            return "Commande non existante", 404
        
        orderDict = model_to_dict(order)
        if orderDict["shippingInformation"] == None and orderDict["email"] == None:
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
                return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque3 un ou plusieurs champs qui sont obligatoires"}}})), 422

            shipping_information = ShippingInformation.create(
                country = country_received,
                address = address_received,
                postalCode = postal_code_received,
                city = city_received,
                province = province_received
            )

            order.email = email_received
            order.shippingInformation = shipping_information
            order.save()
            
            order = model_to_dict(order)
            if order["transaction"] == None:
                order["transaction"] = {}
            if order["creditCard"] == None:
                order["creditCard"] = {}
            if order["shippingInformation"] == None:
                order["shippingInformation"] = {}
            orderProduct = OrderProduct.get_by_id(id)
            orderProduct = model_to_dict(orderProduct)
            order["product"] = { "id":orderProduct["id"], "quantity":orderProduct["quantity"]}
            res = make_response(jsonify({"order" : order}), 200)
            return res, 200
    
        elif orderDict["creditCard"] is None:          
            req = request.get_json()
            credit_card_received = req.get("credit_card")
            if credit_card_received is None:
                return make_response(jsonify({"errors" : {"order": {"code" : "missing-fields", "name" : "Il manque4 un ou plusieurs champs qui sont obligatoires"}}})), 422
            if orderDict["paid"] == True:
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
            
            json_to_send = {
                    "credit_card" : {
                        "name" : name_received,
                        "number" : number_received,
                        "expiration_year" : expiration_year_received,
                        "cvv" : cvv_received,
                        "expiration_month" : expiration_month_received
                    },
                    "amount_charged" : orderDict["totalPrice"] + orderDict["shippingPrice"]
                }
                
            url = 'http://jgnault.ddns.net/shops/pay/'
            json_data = requests.post(url, data=json.dumps(json_to_send)).json()
            
            if json_data.get("errors") is not None:
                return make_response(json_data['transaction']), 422
            
            transaction_received = json_data.get("transaction")
            id_received = transaction_received.get("id")
            success_received = transaction_received.get("success")
            amount_charged_received = transaction_received.get("amount_charged")
    
            credit_card = CreditCard.create(
                name = name_received,
                firstDigits = first_digits_received,
                lastDigits = last_digits_received,
                expirationYear = expiration_year_received,
                expirationMonth = expiration_month_received
            )
            
            transaction = Transaction.create(
                id = id_received,
                success = success_received,
                amountCharged = amount_charged_received,
            )
                
            order.paid = True
            order.creditCard = credit_card
            order.transaction = transaction
            order.save()           
    
            order = model_to_dict(order)
            if order["transaction"] == None:
                order["transaction"] = {}
            if order["creditCard"] == None:
                order["creditCard"] = {}
            if order["shippingInformation"] == None:
                order["shippingInformation"] = {}
            orderProduct = OrderProduct.get_by_id(id)
            orderProduct = model_to_dict(orderProduct)
            order["product"] = { "id":orderProduct["id"], "quantity":orderProduct["quantity"]}
            res = make_response(jsonify({"order" : order}), 200)
            return res, 200          

@app.cli.command("init-db")
@with_appcontext
def init_db_command():
    database = SqliteDatabase(DATABASE)
    if os.path.exists("products.sqlite"):
        os.remove("products.sqlite")
    create_tables()
    click.echo("Initialized the database.")

def initialize():
    app.cli.add_command(init_db_command)

if __name__ == '__main__':
    initialize()
    app.run()