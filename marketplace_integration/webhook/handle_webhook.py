import frappe
import requests
from frappe import _
from frappe.utils import cint, cstr, get_datetime
import json
import hashlib
import time
from urllib.parse import quote
import urllib.parse
from marketplace_integration.lazada import LazopClient, LazopRequest, Client
from datetime import datetime
from erpnext.selling.doctype.sales_order.sales_order import create_pick_list,make_sales_invoice
from erpnext.stock.doctype.pick_list.pick_list import create_delivery_note
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from datetime import datetime, timedelta
import hmac




@frappe.whitelist(allow_guest=True)
def push_wc_webhook(**kwargs):
    if 'order' in kwargs:
        order_data = kwargs['order']
        order_number = order_data.get('order_number')
        status = order_data.get('status')
        buyer_id =  order_data.get('customer_id')
        try:
            contact = frappe.new_doc("Marketplace Logs")
            contact.order_id = order_number
            contact.shope_id = "clinton.co.th"
            contact.status = status
            contact.marketplace = "Website"
            contact.buyer_id = order_data.get('customer_id')
            contact.insert(ignore_permissions=True)
            connect = WcMarketplaceClient()	
            return connect.handle_wc_order_status( order_number,status,order_data,buyer_id,contact.name)
        except Exception:
            pass

class WcMarketplaceClient:
    def handle_wc_order_status(self, ordersn, status, order_data,buyer_id, log_name):
        return self.handle_wc_status(ordersn, status, order_data, buyer_id, log_name)

    def handle_wc_status(self, ordersn, status, order_data, buyer_id, log_name):
        customer_key = self.inser_customer(order_data, buyer_id)
        product = self.check_product_sku(order_data)
        if product:
            frappe.set_user("Administrator")  
            sale_order = self.create_sales_order(order_data,customer_key)
            if sale_order:
                frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
            if status == 'processing':
                self.create_pack_list(sale_order)
                self.create_delivery_note(sale_order,ordersn)
                self.create_sales_invoice(sale_order)   
            elif  status == 'completed':
                self.create_payment_entry(ordersn)
        else:
            order_issue = self.create_order_issue(order_data,customer_key)
            frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)
    

    def create_order_issue(self, order, customer_key):
        try:
            existing_doc = frappe.get_doc("Marketplace order Issue", {"marketplace_order_number": order['order_sn']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Marketplace order Issue')
            new_order.customer = customer_key
            new_order.due_date = datetime.now().date()
            new_order.marketplace_order_number = order.get('order_number', '')
            for item in order['line_items']:
                pprice = item.get("price")
                sku = item.get("sku")
                item_name = item['name']
                new_order.append("items",{
                    "item": item_name[:140],
                    "quantity": item['quantity'],
                    "price": pprice
                })
            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Website"
            new_order.insert(ignore_permissions=True)
            frappe.db.commit()
            return new_order.name
        
    def create_payment_entry(self, ordersn):
        try:
            sales_invoice = frappe.get_doc("Sales Invoice", {"marketplace_order_number": ordersn})
            doc = get_payment_entry("Sales Invoice", sales_invoice.name)
            olddate = datetime.now()
            olddate_str = olddate.strftime("%Y-%m-%d")
            doc.reference_no = ordersn
            doc.reference_date = olddate_str
            doc.mode_of_payment = "Bank Draft"
            doc.save(ignore_permissions=True)
            #doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass
    
    def create_sales_invoice(self, sale_order):
        doc = make_sales_invoice(sale_order,ignore_permissions=True)
        doc.custom_channel = "Shopee"
        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc


    def create_delivery_note(self, sale_order,ordersn):
        picklist = frappe.get_doc("Pick List", {"marketplace_order_number": ordersn})
        try:
            picklist = frappe.get_doc("Pick List", {"marketplace_order_number": ordersn})
            doc = create_delivery_note(picklist.name)
            doc.save(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass

    def create_pack_list(self,sale_order):
        doc = create_pick_list(sale_order)
        doc.submit()
        frappe.db.commit()
        return doc

    def create_sales_order(self, order, customer_key):
        
        
        try:
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": order['order_number']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Sales Order')
            new_order.customer = customer_key
            new_order.delivery_date = datetime.now().date()
            new_order.marketplace_order_number = order.get('order_number', '')
            taxs = self.get_listof_taxs()
            for item in order['line_items']:
                pprice = item.get("price")
                total_tax = item.get("total_tax")
                pprice = pprice+total_tax
                sku = item.get("sku")
                new_order.append("items", {
                    "item_code": sku,
                    "rate" : pprice,
                    "price": pprice,
                    "amount": pprice,
                    "base_rate": pprice,
                    "base_amount": pprice,
                    "stock_uom_rate": pprice,
                    "net_rate": pprice,
                    "net_amount": pprice,
                    "base_net_rate": pprice,
                    "base_net_amount": pprice,
                    "qty":  item['quantity']
                })
            for item in taxs:
                new_order.append("taxes",item)
            if order.get('shipping_lines'):
                new_order.append("taxes", {
                    "charge_type": "Actual",
                    "account_head": "2132-01 WHT PND1",
                    "description": order.get('shipping_lines')[0]["method_title"],
                    "tax_amount": order.get('shipping_lines')[0]["total"]
                })
            new_order.disable_rounded_total = 1
            new_order.taxes_and_charges = 'Thailand Tax - Clinton'
            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Website"
            new_order.insert(ignore_permissions=True)
            new_order.submit()
            frappe.db.commit()
            return new_order.name

    def get_listof_taxs(self):
        doc = frappe.get_doc("Sales Taxes and Charges Template","Thailand Tax - Clinton")
        taxs = doc.taxes
        return taxs

    def check_product_sku(self, order_data):
        for item in order_data["line_items"]:
            sku = item["sku"]
            exists = frappe.db.exists("Item", sku, cache=False)
            if not exists:
                return 0
            else:
                bins = frappe.get_all('Bin', filters={'item_code': sku}, fields=['actual_qty'])
                if bins:
                    return 1
                else:
                    return 0


    def inser_customer(self,order_data, buyer_id):
        try:
            existing_customer = frappe.get_doc("Customer", {"marketplace_buyer_id": buyer_id})
            return existing_customer.name
        except frappe.DoesNotExistError:
            address_data = order_data["billing_address"]
            name = address_data['first_name'] +" "+ address_data['last_name']

            customer = frappe.get_doc({
                "doctype": "Customer",
                "full_name": name,
                "customer_name": name,
                "customer_group": "All Customer Groups",
                "territory": "Thailand",
                "marketplace_buyer_id": buyer_id
            })
            customer.insert(
                ignore_permissions=True
            )
            frappe.db.commit()
            self.create_contact_for_customer(customer.name, address_data)
            return customer.name
        
    def create_contact_for_customer(self,customer, address_data):
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": address_data['first_name'],
            "last_name": address_data['last_name'],
            "address_line1": address_data['address_1'],
            "address_type": "Shipping",
            "customer": customer,
            "is_primary_contact": True
        })
        contact.append('links', {
                'link_doctype': 'Customer',
                'link_name': customer
        })
        contact.append('phone_nos', {
                'phone':  address_data["phone"],
        })
        contact.insert(ignore_permissions=True)
        frappe.db.commit()
        return contact

@frappe.whitelist(allow_guest=True)
def push_shopee_webhook(ordersn,shop_id,status):
    try:
        contact = frappe.new_doc("Marketplace Logs")
        contact.order_id = ordersn
        contact.status = status
        contact.shope_id = shop_id
        contact.marketplace = "Shopee"
        contact.insert(ignore_permissions=True)
        connect = ShopeeMarketplaceClient()	
        return connect.handle_shopee_order_status ( ordersn,shop_id,status,contact.name)
    except Exception:
        pass



class ShopeeMarketplaceClient:
    def handle_shopee_order_status( self, ordersn,shop_id,status,log_name):
        return self.handle_shopee_status(ordersn,shop_id,status,log_name)
    




    def handle_shopee_status(self,ordersn,shop_id,status,log_name):

        

        order = self.shopee_order_details(ordersn)

        customer_key = self.inser_customer(order,order['buyer_user_id'])
        product = self.check_product_sku(order)

        if product:
            frappe.set_user("Administrator")  
            sale_order = self.create_sales_order(order,customer_key)
            if sale_order:
                frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
                
            if status == 'READY_TO_SHIP':
                self.create_pack_list(sale_order)
            elif  status == 'PROCESSED':
                self.create_delivery_note(sale_order,ordersn)
                self.create_sales_invoice(sale_order)   
            elif  status == 'COMPLETED':
                self.create_payment_entry(ordersn)
                self.create_purchase_invoice(ordersn)   
        else:
            order_issue = self.create_order_issue(order,customer_key)
            frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)



    def get_payment_details(self, ordersn):
        partner_id = int(2004610)
        partner_key = "da22ac428afd591add1e4a988eaff7b7981d66980b19323d7d5a5c19116e575a"
        shop_id = int(213497319)

        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_value('access_token')
        kwargs = {
            'order_sn': ordersn
        }
        shopee  = Client(shop_id, partner_id, partner_key, accesstoken)
        shopee.set_access_token(accesstoken)
        shopee  = shopee.execute('payment/get_escrow_detail', "GET", kwargs)
        return shopee['response']["order_income"]




    def create_purchase_invoice(self, ordersn):
        expenss = self.get_payment_details(ordersn)

        commison_fee = expenss["commission_fee"]
        servicefee = expenss["service_fee"]
        transaction_fee = expenss["credit_card_transaction_fee"]
        transaction_fee = commison_fee+servicefee+transaction_fee

        buyer_paid_shipping_fee = expenss["buyer_paid_shipping_fee"]
        actual_shipping_fee = expenss["final_shipping_fee"]

        ordershipping = abs(buyer_paid_shipping_fee)-abs(actual_shipping_fee)

        
        try:
             existing_doc = frappe.get_doc("Purchase Invoice", {"marketplace_order_number": ordersn})
             return existing_doc.name
        except frappe.DoesNotExistError:
            new_invoice = frappe.new_doc('Purchase Invoice')
            new_invoice.supplier = "Shopee Thailand Co.,Ltd.",
            new_invoice.owner_department = "API Admin - Clinton"
            new_invoice.marketplace_order_number = ordersn
            new_invoice.append("items", {
                "item_code": "1234",
                "item_name": "Total Fees and Service Charges",
                "rate" : transaction_fee,
                "qty": 1
            })
            if ordershipping:
                new_invoice.append("items", {
                    "item_code": "1234",
                    "item_name": "Total Delivery Fee",
                    "rate" : ordershipping,
                    "qty": 1
                })
            new_invoice.save()
            new_invoice.submit()
            doc = get_payment_entry("Purchase Invoice", new_invoice.name)
            olddate = datetime.now()
            olddate_str = olddate.strftime("%Y-%m-%d")
            doc.reference_no = ordersn
            doc.reference_date = olddate_str
            doc.mode_of_payment = "Shopee Fee"
            doc.save(ignore_permissions=True)
            doc.submit()
            
            frappe.db.commit()

    def create_payment_entry(self, ordersn):
        try:
            sales_invoice = frappe.get_doc("Sales Invoice", {"marketplace_order_number": ordersn})
            doc = get_payment_entry("Sales Invoice", sales_invoice.name)
            olddate = datetime.now()
            olddate_str = olddate.strftime("%Y-%m-%d")
            doc.reference_no = ordersn
            doc.reference_date = olddate_str
            doc.mode_of_payment = "Shopee Fee"
            doc.save(ignore_permissions=True)
            #doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass


    def create_sales_invoice(self, sale_order):
        doc = make_sales_invoice(sale_order,ignore_permissions=True)
        doc.custom_channel = "Shopee"
        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc

    def create_delivery_note(self, sale_order,ordersn):
        picklist = frappe.get_doc("Pick List", {"marketplace_order_number": ordersn})
        try:
            picklist = frappe.get_doc("Pick List", {"marketplace_order_number": ordersn})
            doc = create_delivery_note(picklist.name)
            doc.save(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass

    def create_pack_list(self,sale_order):
        doc = create_pick_list(sale_order)
        doc.submit()
        frappe.db.commit()
        return doc

    def create_sales_order(self, order, customer_key):
        try:
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": order['order_sn']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Sales Order')
            new_order.customer = customer_key
            new_order.delivery_date = datetime.now().date()
            new_order.marketplace_order_number = order.get('order_sn', '')

            platform_voucher = 0
            seller_voucher = 0
            discounttotal = 0

            #$totalz = $order["price"]+$shipping_price;
            

            
            taxs = self.get_listof_taxs()

            for item in order['item_list']:
                pprice = item.get("model_discounted_price")
                if not pprice:
                    pprice = item.get("model_original_price")
                    
                    
                sku = item.get("item_sku")
                if not sku:
                    sku = item.get("model_sku")
                    
                new_order.append("items", {
                    "item_code": sku,
                    "rate" : pprice,
                    "price": pprice,
                    "amount": pprice,
                    "base_rate": pprice,
                    "base_amount": pprice,
                    "stock_uom_rate": pprice,
                    "net_rate": pprice,
                    "net_amount": pprice,
                    "base_net_rate": pprice,
                    "base_net_amount": pprice,
                    "qty": 1
                })
                
                
            for item in taxs:
                new_order.append("taxes",item)

            new_order.disable_rounded_total = 1
            new_order.taxes_and_charges = 'Thailand Tax - Clinton'



            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Shopee"

            new_order.insert(ignore_permissions=True)
            new_order.submit()
            frappe.db.commit()
            return new_order.name



    def get_listof_taxs(self):
        doc = frappe.get_doc("Sales Taxes and Charges Template","Thailand Tax - Clinton")
        taxs = doc.taxes
        return taxs


    def create_order_issue(self, order, customer_key):
        try:
            existing_doc = frappe.get_doc("Marketplace order Issue", {"marketplace_order_number": order['order_sn']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Marketplace order Issue')
            new_order.customer = customer_key
            new_order.due_date = datetime.now().date()
            new_order.marketplace_order_number = order['order_sn']
            for item in order['item_list']:
                pprice = item.get("model_discounted_price")
                if not pprice:
                    pprice = item.get("model_original_price")

                item_name = item['item_name']
                new_order.append("items",{
                    "item": item_name[:140],
                    "quantity": item['model_quantity_purchased'],
                    "price": pprice
                })
            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Shopee"
            new_order.insert(ignore_permissions=True)
            frappe.db.commit()
            return new_order.name

    def check_product_sku(self, order_info):
        for item in order_info["item_list"]:
            sku = item["item_sku"]
            if not sku:
                sku = item["model_sku"]

            exists = frappe.db.exists("Item", sku, cache=False)
            if not exists:
                return 0
            else:
                bins = frappe.get_all('Bin', filters={'item_code': sku}, fields=['actual_qty'])
                if bins:
                    return 1
                else:
                    return 0
    

    def inser_customer(self, order, buyer_id):
        try:
            existing_customer = frappe.get_doc("Customer", {"marketplace_buyer_id": buyer_id})
            return existing_customer.name
        except frappe.DoesNotExistError:
            address_data = order["recipient_address"]
            name = address_data['name']
            if name == "****":
                name = order["buyer_username"]

            customer = frappe.get_doc({
                "doctype": "Customer",
                "full_name": name,
                "customer_name": name,
                "customer_group": "All Customer Groups",
                "territory": "Thailand",
                "marketplace_buyer_id": buyer_id
            })
            customer.insert(
                ignore_permissions=True
            )
            frappe.db.commit()
            self.create_contact_for_customer(customer.name, name)
            return customer.name

    def create_contact_for_customer(self,customer, name):
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": name,
            "last_name": name,
            "address_line1": name,
            "address_type": "Shipping",
            "customer": customer,
            "is_primary_contact": True
        })
        contact.append('links', {
                'link_doctype': 'Customer',
                'link_name': customer
        })
        # contact.append('phone_nos', {
        #         'phone':  customer_info["phone"],
        # })
        contact.insert(ignore_permissions=True)
        frappe.db.commit()
        return contact
    

    def ced_shopee_get_signature(self,action='', time='', token='', shopid=''):
        base_string = f'2004610/api/v2/{action}{time}{token}{shopid}'
        secret_key = 'da22ac428afd591add1e4a988eaff7b7981d66980b19323d7d5a5c19116e575a'
        signature = hmac.new(secret_key.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature
    





    





    

    def shopee_order_details(self,ordersn):
        partner_id = int(2004610)
        partner_key = "da22ac428afd591add1e4a988eaff7b7981d66980b19323d7d5a5c19116e575a"
        shop_id = int(213497319)

        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_value('access_token')
        kwargs = {
            'order_sn_list': ordersn,
            'response_optional_fields': 'buyer_user_id,buyer_username,estimated_shipping_fee,recipient_address,actual_shipping_fee,goods_to_declare,note,note_update_time,item_list,pay_time,dropshipper,credit_card_number,dropshipper_phone,split_up,buyer_cancel_reason,cancel_by,cancel_reason,actual_shipping_fee_confirmed,buyer_cpf_id,fulfillment_flag,pickup_done_time,package_list,shipping_carrier,payment_method,total_amount,buyer_username,invoice_data,checkout_shipping_carrier,reverse_shipping_fee,model_discounted_price,total_value,products_total_value,tax_code,reverse_shipping_fee,DiscountAmount'
        }
        shopee  = Client(shop_id, partner_id, partner_key, accesstoken)
        shopee.set_access_token(accesstoken)
        shopee  = shopee.execute("order/get_order_detail", "GET", kwargs)
        return shopee['response']['order_list'][0]



@frappe.whitelist(allow_guest=True)
def push_shopee_lazada(ordersn,shop_id,status,buyer_id):
    try:
        contact = frappe.new_doc("Marketplace Logs")
        contact.order_id = ordersn
        contact.status = status
        contact.shope_id = shop_id
        contact.buyer_id = buyer_id
        contact.marketplace = "Lazada"
        contact.insert(ignore_permissions=True)
        connect = LazadaMarketplaceClient()	
        return connect.handle_lazada_order_status ( ordersn,shop_id,status,buyer_id,contact.name)
    except Exception:
        pass
      
class LazadaMarketplaceClient:
    def handle_lazada_order_status( self, ordersn,shop_id,status,buyer_id,log_name):
        order_info =  self.get_order_info(ordersn)
        if order_info:
            
            order_details_json = json.loads(order_info.get('order_details', '[]'))
            order_items = json.loads(order_info.get('order_items', '[]'))
            order_details = order_details_json.get('data', '[]')
            order_items = order_items.get('data', '[]')

            customer_key = self.inser_customer(order_details,buyer_id)
            product = self.check_product_sku(order_items)
            
            if product:
                frappe.set_user("Administrator")  
                
                sale_order = self.create_sales_order(order_details,order_items,customer_key)
                if sale_order:
                    frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
                if status.lower() == 'pending':
                    self.create_pack_list(sale_order)
                elif  status.lower() == 'ready_to_ship':
                    self.create_delivery_note(sale_order,ordersn)
                    self.create_sales_invoice(sale_order)   
                elif  status.lower() == 'delivered':
                    self.create_payment_entry(ordersn)
                    self.create_purchase_invoice_lazada(ordersn)
                elif  status.lower() == 'devtest':
                    return self.create_purchase_invoice_lazada(ordersn)

            else:
                order_issue = self.create_order_issue(order_details,order_items,customer_key)
                if order_issue:
                    frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)
 

    def create_purchase_invoice_lazada(self, ordersn):
        expenss = self.getorderdetails_addional_expenss(ordersn)
        
        paymentfee = self.get_amount_by_fee_type(expenss,"3")
        commission = float(self.get_amount_by_fee_type(expenss,"16"))
        freeshipmax = float(self.get_amount_by_fee_type(expenss,"298"))
        lcpfee = float(self.get_amount_by_fee_type(expenss,"304"))
        subcide = float(self.get_amount_by_fee_type(expenss,"1028"))       
        commission = paymentfee+commission+freeshipmax+lcpfee

        try:
             existing_doc = frappe.get_doc("Purchase Invoice", {"marketplace_order_number": ordersn})
             return existing_doc.name
        except frappe.DoesNotExistError:
            new_invoice = frappe.new_doc('Purchase Invoice')
            new_invoice.supplier = "Lazada Co., Ltd",
            new_invoice.owner_department = "API Admin - Clinton"
            new_invoice.marketplace_order_number = ordersn
            new_invoice.append("items", {
                "item_code": "1234",
                "item_name": "Total Fees and Service Charges",
                "rate" : commission,
                "qty": 1
            })

            if subcide:
                new_invoice.append("items", {
                    "item_code": "1234",
                    "item_name": "Total Delivery Fee",
                    "rate" : subcide,
                    "qty": 1
                })
            new_invoice.save()
            new_invoice.submit()
            doc = get_payment_entry("Purchase Invoice", new_invoice.name)
            olddate = datetime.now()
            olddate_str = olddate.strftime("%Y-%m-%d")
            doc.reference_no = ordersn
            doc.reference_date = olddate_str
            doc.mode_of_payment = "Lazada Fee"
            doc.save(ignore_permissions=True)
            doc.submit()
            
            frappe.db.commit()
            

        
        

    
    def get_amount_by_fee_type(self, data, fee_type):
        amounts = [entry['amount'] for entry in data if entry.get('fee_type') == fee_type]
        if amounts:
            return abs(float(amounts[0]))
        else:
            return 0 





    def create_payment_entry(self, ordersn):
        try:
            sales_invoice = frappe.get_doc("Sales Invoice", {"marketplace_order_number": ordersn})
            doc = get_payment_entry("Sales Invoice", sales_invoice.name)
            olddate = datetime.now()
            olddate_str = olddate.strftime("%Y-%m-%d")
            doc.reference_no = ordersn
            doc.reference_date = olddate_str
            doc.mode_of_payment = "Lazada Fee"
            doc.save(ignore_permissions=True)
            #doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass

    def create_sales_invoice(self, sale_order):
        doc = make_sales_invoice(sale_order,ignore_permissions=True)
        doc.custom_channel = "Lazada"
        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc
    
    
    def create_delivery_note(self, sale_order,ordersn):
        picklist = frappe.get_doc("Pick List", {"marketplace_order_number": ordersn})
        try:
            picklist = frappe.get_doc("Pick List", {"marketplace_order_number": ordersn})
            doc = create_delivery_note(picklist.name)
            doc.save(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass
        
    def create_pack_list(self,sale_order):
        doc = create_pick_list(sale_order)
        doc.save(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc
    
    
    def create_sales_order(self, order_details, order_items, customkey):
        try:
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": order_details['order_number']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Sales Order')
            new_order.customer = customkey
            new_order.delivery_date = datetime.now().date()
            new_order.marketplace_order_number = order_details.get('order_number', '')

            platform_voucher = 0
            seller_voucher = 0
            discounttotal = 0

            #$totalz = $order["price"]+$shipping_price;
            

            
            taxs = self.get_listof_taxs()

            for item in order_items:
                new_order.append("items", {
                    "item_code": item['sku'],
                    "rate" : item['item_price'],
                    "price": item['item_price'],
                    "amount": item['item_price'],
                    "base_rate": item['item_price'],
                    "base_amount": item['item_price'],
                    "stock_uom_rate": item['item_price'],
                    "net_rate": item['item_price'],
                    "net_amount": item['item_price'],
                    "base_net_rate": item['item_price'],
                    "base_net_amount": item['item_price'],
                    "qty": 1
                })
                platform_voucher += item.get('voucher_platform', 0)
                seller_voucher += item.get('voucher_seller', 0)
                discounttotal += item.get('voucher_amount', 0)
                

            ordertotal = float(order_details["price"]) + float(order_details["shipping_fee"])
            grand_total_marketplace = ordertotal-discounttotal

        


            if seller_voucher:
                new_order.append("custom_seller_voucher",{
                    "doctype": 'Seller Voucher List',
                    "voucher_name": 'Seller Discount',
                    "voucher_amount": seller_voucher
                })


            for item in taxs:
                new_order.append("taxes",item)

            new_order.disable_rounded_total = 1
            if platform_voucher:
                new_order.custom_marketplace_discount = platform_voucher


            new_order.custom_grand_total_marketplace = grand_total_marketplace
            new_order.discount_amount = seller_voucher
            new_order.custom_marketplace_taxes_and_charges = float(order_details["shipping_fee"])
            new_order.taxes_and_charges = 'Thailand Tax - Clinton'



            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Lazada"

            new_order.insert(ignore_permissions=True)
            new_order.submit()
            frappe.db.commit()
            return new_order.name


    def get_listof_taxs(self):
        doc = frappe.get_doc("Sales Taxes and Charges Template","Thailand Tax - Clinton")
        taxs = doc.taxes
        return taxs

    def map_sales_order_to_pick_list(self,source_name):
        new_picl_list = frappe.new_doc('Pick List')
        new_picl_list.parent_warehouse = "HQ (คลังหลัก) - Clinton"
        new_picl_list.company = "CLINTON INTERTRADE COMPANY LIMITED"
        new_picl_list.marketplace_platform = "Lazada"
        new_picl_list.marketplace_order_number = "123123123"
        new_picl_list.insert(ignore_permissions=True)
        return new_picl_list


    def create_order_issue(self, order_details, order_items, customkey):
        try:
            existing_doc = frappe.get_doc("Marketplace order Issue", {"marketplace_order_number": order_details['order_number']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Marketplace order Issue')
            new_order.customer = customkey
            new_order.due_date = datetime.now().date()
            new_order.marketplace_order_number = order_details.get('order_number', '')
            for item in order_items:
                new_order.append("items",{
                    "item": item['name'],
                    "quantity": 1,
                    "price": item['paid_price'],
                    "amount": item['paid_price']
                })
            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Lazada"
            new_order.insert(ignore_permissions=True)
            frappe.db.commit()
            return new_order.name
        

    def check_product_sku(self, order_info):
        for item in order_info:
            sku = item["sku"]
            exists = frappe.db.exists("Item", sku, cache=False)
            if not exists:
                return 0
            else:
                bins = frappe.get_all('Bin', filters={'item_code': sku}, fields=['actual_qty'])
                if bins:
                    return 1
                else:
                    return 0

    def inser_customer(self, order_details, buyer_id):
        customer_info = order_details['address_shipping'] 
        name = customer_info["first_name"] + customer_info["last_name"]
        try:
            existing_customer = frappe.get_doc("Customer", {"marketplace_buyer_id": buyer_id})
            return existing_customer.name
        except frappe.DoesNotExistError:
            customer = frappe.get_doc({
                "doctype": "Customer",
                "full_name": name,
                "customer_name": name,
                "customer_group": "All Customer Groups",
                "territory": "Thailand",
                "marketplace_buyer_id": buyer_id
            })
            customer.insert(
                ignore_permissions=True
            )
            frappe.db.commit()
            self.create_contact_for_customer(customer.name, customer_info)
            return customer.name

            
    def create_contact_for_customer(self,customer, customer_info):
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": customer_info["first_name"],
            "last_name": customer_info["last_name"],
            "address_line1": customer_info["address1"],
            "address_type": "Shipping",
            "customer": customer,
            "is_primary_contact": True
        })
        contact.append('links', {
                'link_doctype': 'Customer',
                'link_name': customer
        })
        contact.append('phone_nos', {
                'phone':  customer_info["phone"],
        })
        contact.insert(ignore_permissions=True)
        frappe.db.commit()
        return contact

    
    def getorderdetails_addional_expenss( self, ordersn):
        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_password('lazada_access_token')
        if accesstoken:
            olddate = datetime.now() - timedelta(days=4*30)
            olddate_str = olddate.strftime("%Y-%m-%d")
            client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
            request = LazopRequest('/finance/transaction/details/get','GET')
            request.add_api_param('start_time', olddate_str)
            request.add_api_param('end_time', datetime.now().strftime("%Y-%m-%d"))
            request.add_api_param('trade_order_id', ordersn)
            order_details = client.execute(request, accesstoken).body
            return order_details["data"]
        
        
        
    def get_order_info( self, ordersn):
        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_password('lazada_access_token')
        order_data = {}
        if accesstoken:
            client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
            request = LazopRequest('/order/get','GET')
            request.add_api_param('order_id', ordersn)
            order_details = client.execute(request, accesstoken).body


            if order_details:
                order_details = json.dumps(order_details)
                client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
                request = LazopRequest('/order/items/get','GET')
                request.add_api_param('order_id', ordersn)
                response_items = client.execute(request, accesstoken).body
                response_items = json.dumps(response_items)
                order_data['order_details'] = order_details
                order_data['order_items'] = response_items

            return order_data



    



    
    