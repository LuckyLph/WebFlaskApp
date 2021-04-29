from flask import g
from flask import Flask
from flask import current_app
from flask.cli import with_appcontext
import json
import sqlite3
import requests
from peewee import *
import click
import os

DATABASE = 'products.sqlite'
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

    class Meta:
        tableName = "products"

class ShippingInformation(BaseModel):
    id = IntegerField(primary_key=True, index= True)
    country = TextField(null = True)
    address = TextField(null = True)
    postalCode = TextField(null = True)
    city = TextField(null = True)
    province = TextField(null = True)

    class Meta:
        table_name = "shippingInformations"

class CreditCard(BaseModel):
    id = IntegerField(primary_key=True, index= True)
    name = TextField(null = True)
    firstDigits = TextField(null = True)
    lastDigits = TextField(null = True)
    expirationYear = TextField(null = True)
    expirationMonth = TextField(null = True)

    class Meta:
        table_name = "creditCards"

class Error(BaseModel):
    code = TextField(null = True)
    name = TextField(null = True)

    class Meta:
        table_name = "errors"

class Transaction(BaseModel):
    id = TextField(primary_key=True, unique=True)
    success = BooleanField(null = True)
    error = ForeignKeyField(Error, null = True)
    amountCharged = FloatField(null = True)

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
        database.drop_tables([Product, ShippingInformation, CreditCard, Error, Transaction, Order, OrderProduct])
        database.create_tables([Product, ShippingInformation, CreditCard, Error, Transaction, Order, OrderProduct])
        
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
        
def initialize(app):
    app.cli.add_command(init_db_command)
    
@click.command("init-db")
@with_appcontext
def init_db_command():
    database = SqliteDatabase(DATABASE)
    if os.path.exists("products.sqlite"):
        os.remove("products.sqlite")
    create_tables()
    click.echo("Initialized the database.")