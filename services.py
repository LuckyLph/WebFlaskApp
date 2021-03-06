from flask import Flask, request, jsonify, make_response
from flask import redirect
from flask import session
from flask.cli import with_appcontext
from flask import url_for, abort, render_template, flash
from playhouse.shortcuts import model_to_dict, dict_to_model
from functools import wraps
from hashlib import md5
from peewee import *
import json
import click
import requests
import models
import os
import psycopg2
import redis
from redis import Redis
from rq import Queue, Worker

REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
redis_cache = redis.Redis(REDIS_HOST)
#redis = Redis.from_url("redis://localhost")
task_manager = Queue(connection=redis_cache)

def create_app(configuration = None):
    app = Flask(__name__, instance_relative_config=True)

    if configuration != None:
        app.config.update(configuration)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    models.initialize(app)
    #app.cli.add_command(rq_worker)

    @app.route('/')
    def products():  
        response = list(models.Product.select().dicts())
        res = make_response(jsonify({"products" : response}), 200)
        return res, 200  

    @app.route('/order', methods=['POST'])
    def create_order():
        if request.is_json:
            req = request.get_json()
            product_received = req.get("products")
            totalPrice = 0
            weight = 0
            for i in product_received:                
                if i is None:
                    return make_response(jsonify({"errors" : {"product": {"code" : "missing-fields", "name" : "La création d'une commande nécessite un produit"}}})), 422
                id_received = i.get("id")
                quantity_received = i.get("quantity")
                if id_received is None or quantity_received is None:
                    return make_response(jsonify({"errors" : {"product": {"code" : "missing-fields", "name" : "La création d'une commande nécessite un produit"}}})), 422
                if request.method == 'POST':
                    try:
                        product = models.Product.get_by_id(i["id"])
                    except DoesNotExist:
                        product = None
                    if product != None and product.inStock:
                        totalPrice += product.price * quantity_received
                        weight += product.weight * quantity_received       
                    else:
                        return make_response(jsonify({"errors" : {"product": {"code" : "out-of-inventory", "name" : "Le produit demandé n'est pas en inventaire"}}})), 422
                else:
                    return "Bad request method", 400
                            
            if weight < 500:
                shippingPrice = 5
            elif weight < 2000:
                shippingPrice = 10
            elif weight >= 2000:
                shippingPrice = 25      
                
            order = models.Order.create(shippingPrice=shippingPrice, totalPrice=totalPrice)
            for i in product_received:
                product = models.Product.get_by_id(i["id"])
                quantity_received = i.get("quantity")
                models.OrderProduct.create(order=order, product=product, quantity=quantity_received)
           
            return make_response(jsonify({"Location" : "order/{0}".format(order.id) })), 302
                
        else:
            return "No JSON received", 400   

    @app.route('/order/<int:id>', methods=['GET', 'PUT'])
    def get_order(id):        
        if request.method == 'GET':         
            try:
                if (id is None):
                    order = None 
                else:
                    # job = task_manager.get(id)
                    # if not job.is_finished:
                        # return ('', 202)
                    order = redis_cache.get(id)
                    if (order is None):
                        order = models.Order.get_by_id(id)
                    else:
                        res = make_response(json.loads(order), 200)
                        return res, 200
            except DoesNotExist:
                order = None
                
            if(order is None):
                return "Commande non existante", 404
        
            order = model_to_dict(order)
            if order["transaction"] == None:
                order["transaction"] = {}
            else:               
                if order["transaction"]["error"] == None:
                    order["transaction"]["error"] = {}
            if order["creditCard"] == None:
                order["creditCard"] = {}
            if order["shippingInformation"] == None:
                order["shippingInformation"] = {}
            order["products"] = list(map(lambda x: { "id":x["product"], "quantity":x["quantity"] }, list(models.OrderProduct.select().where(models.OrderProduct.order == order["id"]).dicts())))
            res = make_response(jsonify({"order" : order}), 200)
            return res, 200
                
        if request.method == 'PUT':
            try:
                if (id is None):
                    order = None 
                else:
                    # job = task_manager.get(id)
                    # if not job.is_finished:
                        # return ('', 409)
                    order = redis_cache.get(id)
                    if (order is None):
                        order = models.Order.get_by_id(id)
                    else:
                        return make_response(jsonify({"errors" : {"order": {"code" : "already-paid", "name" : "La commande a déjà été payée."}}})), 422
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

                shipping_information = models.ShippingInformation.create(
                    country = country_received.replace("\x00", "\uFFFD"),
                    address = address_received.replace("\x00", "\uFFFD"),
                    postalCode = postal_code_received.replace("\x00", "\uFFFD"),
                    city = city_received.replace("\x00", "\uFFFD"),
                    province = province_received.replace("\x00", "\uFFFD")
                )

                order.email = email_received
                order.shippingInformation = shipping_information
                order.save()
                
                order = model_to_dict(order)
                if order["transaction"] == None:
                    order["transaction"] = {}
                else:
                    if order["transaction"]["error"] == None:
                        order["transaction"]["error"] = {}
                if order["creditCard"] == None:
                    order["creditCard"] = {}
                if order["shippingInformation"] == None:
                    order["shippingInformation"] = {}
                orderProduct = models.OrderProduct.get_by_id(id)
                orderProduct = model_to_dict(orderProduct)
                order["products"] = list(map(lambda x: { "id":x["product"], "quantity":x["quantity"] }, list(models.OrderProduct.select().where(models.OrderProduct.order == order["id"]).dicts())))
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
                               
                # json_data = task_manager.enqueue(pay_command)
                
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
                
                if json_data.get("success") is False:
                    error = models.Error.create(
                        code = "card-declined".replace("\x00", "\uFFFD"),
                        name = json_data.get("message").replace("\x00", "\uFFFD")
                    )
                    if (orderDict["transaction"] is not None):
                        transToDel = models.Transaction.get_by_id(id)
                        transToDel.delete_instance()
                    transaction = models.Transaction.create(
                        id = str(id).replace("\x00", "\uFFFD"),
                        success = False,
                        error = error,
                        amountCharged = orderDict["totalPrice"] + orderDict["shippingPrice"]
                    )   
                    order.transaction = transaction
                    order.save()         
                    return make_response(jsonify({"errors" : {"credit_card": {"code" : "card-declined", "name" : "La carte de crédit a été déclinée"}}})), 422             

                credit_card = models.CreditCard.create(
                    name = name_received.replace("\x00", "\uFFFD"),
                    firstDigits = first_digits_received.replace("\x00", "\uFFFD"),
                    lastDigits = last_digits_received.replace("\x00", "\uFFFD"),
                    expirationYear = expiration_year_received,
                    expirationMonth = expiration_month_received
                )
                                
                transaction_received = json_data.get("transaction")
                id_received = transaction_received.get("id")
                success_received = transaction_received.get("success")
                amount_charged_received = transaction_received.get("amount_charged")                
                
                if (orderDict["transaction"] is not None):
                    transToDel = models.Transaction.get_by_id(id)
                    transToDel.delete_instance()
                transaction = models.Transaction.create(
                    id = id_received.replace("\x00", "\uFFFD"),
                    success = success_received,
                    error = None,
                    amountCharged = amount_charged_received,
                )
                    
                order.paid = True
                order.creditCard = credit_card
                order.transaction = transaction
                order.save()           

                order = model_to_dict(order)
                if order["transaction"] == None:
                    order["transaction"] = {}
                else:
                    if order["transaction"]["error"] == None:
                        order["transaction"]["error"] = {}
                if order["creditCard"] == None:
                    order["creditCard"] = {}
                if order["shippingInformation"] == None:
                    order["shippingInformation"] = {}
                orderProduct = models.OrderProduct.get_by_id(id)
                orderProduct = model_to_dict(orderProduct)
                order["products"] = list(map(lambda x: { "id":x["product"], "quantity":x["quantity"] }, list(models.OrderProduct.select().where(models.OrderProduct.order == order["id"]).dicts())))
                res = make_response(jsonify({"order" : order}), 200)
                redis_cache.set(id, json.dumps({"order" : order}))
                return res, 200
                              
                # return ('', 202)
          
            if orderDict["paid"] == True:
                    return make_response(jsonify({"errors" : {"order": {"code" : "already-paid", "name" : "La commande a déjà été payée."}}})), 422

    return app
   
# def pay_command():
    # json_to_send = {
            # "credit_card" : {
                # "name" : name_received,
                # "number" : number_received,
                # "expiration_year" : expiration_year_received,
                # "cvv" : cvv_received,
                # "expiration_month" : expiration_month_received
            # },
            # "amount_charged" : orderDict["totalPrice"] + orderDict["shippingPrice"]
        # }
        
    # url = 'http://jgnault.ddns.net/shops/pay/'
    # json_data = requests.post(url, data=json.dumps(json_to_send)).json()
    
    # if json_data.get("success") is False:
        # error = models.Error.create(
            # code = "card-declined".replace("\x00", "\uFFFD"),
            # name = json_data.get("message").replace("\x00", "\uFFFD")
        # )
        # if (orderDict["transaction"] is not None):
            # transToDel = models.Transaction.get_by_id(id)
            # transToDel.delete_instance()
        # transaction = models.Transaction.create(
            # id = str(id).replace("\x00", "\uFFFD"),
            # success = False,
            # error = error,
            # amountCharged = orderDict["totalPrice"] + orderDict["shippingPrice"]
        # )   
        # order.transaction = transaction
        # order.save()         
        # return make_response(jsonify({"errors" : {"credit_card": {"code" : "card-declined", "name" : "La carte de crédit a été déclinée"}}})), 422             

    # credit_card = models.CreditCard.create(
        # name = name_received.replace("\x00", "\uFFFD"),
        # firstDigits = first_digits_received.replace("\x00", "\uFFFD"),
        # lastDigits = last_digits_received.replace("\x00", "\uFFFD"),
        # expirationYear = expiration_year_received,
        # expirationMonth = expiration_month_received
    # )
                    
    # transaction_received = json_data.get("transaction")
    # id_received = transaction_received.get("id")
    # success_received = transaction_received.get("success")
    # amount_charged_received = transaction_received.get("amount_charged")                
    
    # if (orderDict["transaction"] is not None):
        # transToDel = models.Transaction.get_by_id(id)
        # transToDel.delete_instance()
    # transaction = models.Transaction.create(
        # id = id_received.replace("\x00", "\uFFFD"),
        # success = success_received,
        # error = None,
        # amountCharged = amount_charged_received,
    # )
        
    # order.paid = True
    # order.creditCard = credit_card
    # order.transaction = transaction
    # order.save()           

    # order = model_to_dict(order)
    # if order["transaction"] == None:
        # order["transaction"] = {}
    # else:
        # if order["transaction"]["error"] == None:
            # order["transaction"]["error"] = {}
    # if order["creditCard"] == None:
        # order["creditCard"] = {}
    # if order["shippingInformation"] == None:
        # order["shippingInformation"] = {}
    # orderProduct = models.OrderProduct.get_by_id(id)
    # orderProduct = model_to_dict(orderProduct)
    # order["products"] = list(map(lambda x: { "id":x["product"], "quantity":x["quantity"] }, list(models.OrderProduct.select().where(models.OrderProduct.order == order["id"]).dicts())))
    # res = make_response(jsonify({"order" : order}), 200)
    # redis_cache.set(id, json.dumps({"order" : order}))
    
    # return json_data

# @click.command("worker")
# @with_appcontext
# def rq_worker():
    # worker = Worker([task_manager], connection=redis_cache)
    # worker.work()