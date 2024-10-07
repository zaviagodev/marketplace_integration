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
from erpnext.selling.doctype.sales_order.sales_order import create_pick_list, make_sales_invoice
from erpnext.stock.doctype.pick_list.pick_list import create_delivery_note
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from datetime import datetime, timedelta
import hmac
import pytz


def create_marketplace_log(market, ordersn, status, shop_id, buyer_id, payload):
    marketplace_log = frappe.get_doc({
        "doctype": f"Marketplace {market} Logs",
        "order_id": f"{ordersn}",
        "buyer_id": buyer_id,
        "shop_id": shop_id,
        'status': status,
        "payload": json.dumps(payload),
        "timestamp": datetime.now()
    })
    
    marketplace_log.save()
    frappe.db.commit()

@frappe.whitelist(allow_guest=True)
def handle_delay_event_shopee_queue():
    bangkok_timezone = pytz.timezone('Asia/Bangkok')
    current_time = datetime.now(bangkok_timezone)
    one_hour_ago = current_time - timedelta(hours=1)
    one_hour_ago_str = one_hour_ago.strftime("%Y-%m-%d %H:%M:%S")
    pending_jobs = frappe.get_all("Marketplace Logs", filters={
        "status": "COMPLETED",
        "custom_job_completed": 0,
        "marketplace": "Shopee",
        "creation": ["<", one_hour_ago_str]
    }, fields=["name", "order_id", "status", "shope_id", "creation"])

    if pending_jobs:
        for job in pending_jobs:
            try:
                frappe.enqueue('marketplace_integration.webhook.handle_webhook.handle_delay_event_shopee', 
                               queue='short', 
                               ordersn=job.order_id, 
                               shop_id=job.shope_id, 
                               status=job.status, 
                               log_name=job.name)
                

                frappe.db.set_value("Marketplace Logs", job.name, "custom_job_completed", 1)
                frappe.logger().info(f"Processed job for order_id: {job.order_id}")
            except Exception as e:
                frappe.logger().error(f"Error processing job {job.name}: {str(e)}")


@frappe.whitelist(allow_guest=True)
def handle_delay_event_lazada_queue():
    bangkok_timezone = pytz.timezone('Asia/Bangkok')
    current_time = datetime.now(bangkok_timezone)
    one_hour_ago = current_time - timedelta(hours=1)
    one_hour_ago_str = one_hour_ago.strftime("%Y-%m-%d %H:%M:%S")
    pending_jobs = frappe.get_all("Marketplace Logs", filters={
        "status": "DELIVERED",
        "custom_job_completed": 0,
        "marketplace": "Lazada",
        "creation": ["<", one_hour_ago_str]
    }, fields=["name", "order_id", "status", "shope_id", "creation"])

    if pending_jobs:
        for job in pending_jobs:
            try:
                frappe.enqueue('marketplace_integration.webhook.handle_webhook.handle_delay_event_lazada', 
                               queue='short', 
                               ordersn=job.order_id, 
                               shop_id=job.shope_id, 
                               buyer_id=job.shope_id, 
                               status=job.status, 
                               log_name=job.name)
                
                frappe.db.set_value("Marketplace Logs", job.name, "custom_job_completed", 1)
                frappe.logger().info(f"Processed job for order_id: {job.order_id}")
            except Exception as e:
                frappe.logger().error(f"Error processing job {job.name}: {str(e)}")

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
        if customer_key:
            frappe.db.set_value('Marketplace Logs', log_name, 'custom_customer', customer_key)
        
        product = self.check_product_sku(order_data)
        if product:
            frappe.set_user("Administrator")  
            sale_order = self.create_sales_order(order_data,customer_key)
            if sale_order:
                frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
            if status == 'processing' or status == 'payment-confirmed':
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
        doc.additional_discount_account = "4170-00 SALES DISCOUNT"
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


            current_date = datetime.now().date()
            delivery_date = current_date + timedelta(days=2)
            new_order.delivery_date = delivery_date

            new_order.marketplace_order_number = order.get('order_number', '')
            taxs = self.get_listof_taxs()
            
            
            
            for item in order['line_items']:
                pprice = item.get("subtotal")
                total_tax = item.get("total_tax")
                pprice = pprice
                sku = item.get("sku")
                new_order.append("items", {
                    "item_code": sku,
                    "rate" : pprice,
                    "price_list_rate" : pprice,
                    "base_price_list_rate" : pprice,
                    "qty":  item['quantity']
                })
                
            
            coupons_amount = 0
            if order.get("coupon_lines"):
                for item in order.get("coupon_lines", []): 
                    coupons_amount += float(item.get("amount"))
                    
                if coupons_amount:
                    new_order.discount_amount = coupons_amount
                

           

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
            new_order.selling_price_list = "Website"
            try:
                new_order.insert(ignore_permissions=True)
                new_order.submit()
                frappe.db.commit()
                return new_order.name
            except frappe.DuplicateEntryError:
                return None


            

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
                # bins = frappe.get_all('Bin', filters={'item_code': sku}, fields=['actual_qty'])
                # if bins:
                return 1
                # else:
                #     return 0


    def inser_customer(self,order_data, buyer_id):

        if buyer_id:
            try:
                existing_customer = frappe.get_doc("Customer", {"marketplace_buyer_id": buyer_id})
                return existing_customer.name
            except frappe.DoesNotExistError:
                address_data = order_data["billing_address"]
                name = address_data['first_name'] +" "+ address_data['last_name']
                customer = frappe.get_doc({
                    "doctype": "Customer",
                    "full_name": str(name),
                    "customer_name": "WEB-"+str(buyer_id),
                    "customer_group": "Website",
                    "territory": "Thailand",
                    "marketplace_buyer_id": buyer_id
                })
                customer.insert(
                    ignore_permissions=True
                )
                frappe.db.commit()
                #self.create_contact_for_customer(customer.name, address_data)
                return customer.name
        else:
            return "Guest"
        
    def create_contact_for_customer(self,customer, address_data):
        address_data = address_data["billing_address"]

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


        address = frappe.get_doc({
            "doctype": "Address",
            "address_line1": address_data["address_1"],
            "phone": address_data["phone"],
            "address_type": "Shipping",
            "city": "-",
        })
        address.append('links', {
                'link_doctype': 'Customer',
                'link_name': customer
        })
        address.insert(ignore_permissions=True)
        frappe.db.commit()



        frappe.db.commit()
        return contact
    
@frappe.whitelist(allow_guest=True)
def handle_delay_event_shopee(ordersn,shop_id,status,log_name):
    frappe.logger().info(f"Handling completed order: {ordersn}")
    connect = ShopeeMarketplaceClient()	
    return connect.handle_shopee_order_status ( ordersn,shop_id,status,log_name)

@frappe.whitelist(allow_guest=True)
def push_shopee_webhook(ordersn,shop_id,status):

    
    if status != "COMPLETED":
        try:
            contact = frappe.new_doc("Marketplace Logs")
            contact.order_id = ordersn
            contact.status = status
            contact.shope_id = shop_id
            contact.marketplace = "Shopee"
            contact.custom_job_completed = 1
            contact.insert(ignore_permissions=True)
            frappe.db.commit()
            connect = ShopeeMarketplaceClient()	
            return connect.handle_shopee_order_status ( ordersn,shop_id,status,contact.name)
        except Exception:
            pass
    else:
        contact = frappe.new_doc("Marketplace Logs")
        contact.order_id = ordersn
        contact.status = status
        contact.shope_id = shop_id
        contact.marketplace = "Shopee"
        contact.custom_job_completed = 0
        contact.insert(ignore_permissions=True)
        frappe.db.commit()

@frappe.whitelist(allow_guest=True)
def feach_shopee_orders(**kwargs):
    # frappe.set_user("Administrator")  
    # dd = frappe.db.get_list('Sales Order',
    #     filters={
    #         'item_code': 'SELLER_VOUCHER',
    #         'marketplace_platform': 'Shopee'
    #     },
    #     fields=['marketplace_order_number'],
    #     as_list=True
    # )

   
    # return  dd

    connect = ShopeeMarketplaceClient()

    orderno = kwargs["order"]
    if ',' in kwargs["order"]:
        order_numbers = orderno.split(',') 
        results = []
        for order_number in order_numbers:
            result = connect.handle_feach_shopee_orders(order_number.strip()) 
            if result == 1:
                results.append(order_number)

        return results
    else:
        return connect.handle_feach_shopee_orders(orderno.strip())




@frappe.whitelist(allow_guest=True)
def get_shopee_order_info(order_number):
    connect = ShopeeMarketplaceClient()
    result = connect.handle_feach_shopee_orders(order_number.strip()) 
    return result


@frappe.whitelist(allow_guest=True)
def get_shopee_orders_list(**kwargs):
    frappe.set_user("Administrator")  
    partner_id = int(2004610)
    partner_key = "da22ac428afd591add1e4a988eaff7b7981d66980b19323d7d5a5c19116e575a"
    shop_id = int(213497319)
    docSettings = frappe.get_single("Marketplace integration")
    accesstoken = docSettings.get_value('access_token')
    time_from = datetime(2024, 4, 1).timestamp()
    time_to = datetime(2024, 4, 15).timestamp()
    kwargs = {
        'time_range_field': 'create_time',
        'time_from': int(time_from),
        'time_to': int(time_to),
        'page_size': 100,
        'cursor': kwargs["pageno"],
    }
    shopee  = Client(shop_id, partner_id, partner_key, accesstoken)
    shopee.set_access_token(accesstoken)
    shopee  = shopee.execute("order/get_order_list", "GET", kwargs)

    orderslist =  shopee["response"]["order_list"]

    connect = ShopeeMarketplaceClient()
    results = []
    if orderslist:
            for order in orderslist:
                ordersn = order["order_sn"]
                #order = connect.shopee_order_details(ordersn)
                #status = order["order_status"]
                doc_list = frappe.get_list('Payment Entry', {'reference_no': ordersn})
                for doc in doc_list:
                    frappe.db.delete('Payment Entry', doc["name"])
                results.append(ordersn)

    return results




class ShopeeMarketplaceClient:
    def handle_shopee_order_status( self, ordersn,shop_id,status,log_name):
        return self.handle_shopee_status(ordersn,shop_id,status,log_name)

    def handle_feach_shopee_orders(self,orderno):
        ordersn = orderno
        frappe.set_user("Administrator")  
        order = self.shopee_order_details(ordersn)
        expenss = self.get_payment_details(ordersn)

        return order

        #sale_order = self.create_sales_order(ordersn,order,customer_key)
        


        if orderslist:
            for order in orderslist:
                ordersn = order["order_sn"]
                order = self.shopee_order_details(ordersn)
                
                status = order["order_status"]

                try:
                    frappe.flags.mute_messages = True
                    frappe.get_doc("Sales Order", {"marketplace_order_number": order['order_sn']})
                    
                except frappe.DoesNotExistError:
                    frappe.flags.mute_messages = True
                    customer_key =  self.inser_customer(order,order['buyer_user_id'])
                    product = self.check_product_sku(order)
                    if product:
                        frappe.set_user("Administrator")  
                        sale_order = self.create_sales_order(ordersn,order,customer_key)

                        if status == 'READY_TO_SHIP':
                            self.create_pack_list(sale_order)
                        elif  status == 'PROCESSED':
                            self.create_pack_list(sale_order)
                            self.create_delivery_note(sale_order,ordersn)
                            self.create_sales_invoice(sale_order)   
                        elif  status == 'COMPLETED':
                            self.create_pack_list(sale_order)
                            self.create_delivery_note(sale_order,ordersn)
                            self.create_sales_invoice(sale_order)   
                            self.create_payment_entry(ordersn)
                            self.create_purchase_invoice(ordersn,order)   
                    else:
                        self.create_order_issue(order,customer_key)

        #return self.create_purchase_invoice(ordersn,order)   


        
        
        
        

       


        status = order["order_status"]

        doc_list = frappe.get_list('Purchase Invoice', {'marketplace_order_number': ordersn})
        for doc in doc_list:
            frappe.db.delete('Purchase Invoice', doc["name"])

        return self.create_purchase_invoice(ordersn,order)   


    def handle_shopee_status(self,ordersn,shop_id,status,log_name):

        frappe.flags.mute_exceptions = True
        order = self.shopee_order_details(ordersn)
        customer_key = self.inser_customer(order,order['buyer_user_id'])
        if customer_key:
            frappe.db.set_value('Marketplace Logs', log_name, 'custom_customer', customer_key)
        product = self.check_product_sku(order)
        
        if product:
            frappe.set_user("Administrator")
            payment_details = self.get_payment_details(ordersn)
            if status == 'UNPAID':
                sale_order = self.create_sales_order(ordersn,order,customer_key, payment_details)
                frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
            else:
                if frappe.db.exists("Sales Order", {"marketplace_order_number": ordersn}):
                    sale_order = frappe.get_doc("Sales Order", {"marketplace_order_number": ordersn})
                    frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order.name)
                    sale_order_status = frappe.db.get_value("Sales Order", sale_order.name , ["status"])    
                    if status == 'READY_TO_SHIP':
                        unavailable_items = self.create_pick_list(sale_order)
                        if unavailable_items:
                            create_marketplace_log("Shopee", ordersn, "pending", shop_id, buyer_id, unavailable_items)
                    elif  status == 'PROCESSED':
                        self.create_delivery_note(sale_order.name,ordersn)
                        self.create_sales_invoice(sale_order.name)   
                    elif  status == 'COMPLETED':
                        if sale_order_status == "Completed":
                            if payment_details.get("escrow_amount", 999999999999) <= 0:
                                self.update_sale_invoice_remark(ordersn, "Return/Refund")

                            elif self.calculate_shipping_fee(payment_details) >= 0:
                                self.update_sale_invoice_remark(ordersn, "Positive Shipping Fee")

                            else:
                                update_sale_invoice_remark(ordersn, "Completed")
                                self.create_payment_entry(ordersn)
                                self.create_purchase_invoice(ordersn,order)

        else:
            order_issue = self.create_order_issue(order,customer_key)
            frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)


    def update_sale_invoice_remark(self, ordersn, remark):
        sales_invoice = frappe.get_doc("Sales Invoice", {"marketplace_order_number": ordersn})
        sales_invoice.marketplace_remark = remark
        sales_invoice.save()

    
    def calculate_shipping_fee(self, expense_report):
        collected_shipping_fee = expense_report["buyer_paid_shipping_fee"] + expense_report["shopee_shipping_rebate"]
        actual_shipping_fee = expense_report["actual_shipping_fee"]

        return collected_shipping_fee - actual_shipping_fee

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

    def create_purchase_invoice(self, ordersn,order):
        expenss = self.get_payment_details(ordersn)

        grand_total = 0
        subside = 0
        discount_from_voucher_seller = 0
        grand_total = expenss.get('order_selling_price', 0)
        for item in order["item_list"]:
            discount_from_voucher_seller += float(item.get('discount_from_voucher_seller', 0))
        
        
        commison_fee = expenss["commission_fee"]
        servicefee = expenss["service_fee"]
        transaction_fee = expenss["credit_card_transaction_fee"]
        service_charges = commison_fee+servicefee+transaction_fee
        
        buyer_paid_shipping_fee = expenss["buyer_paid_shipping_fee"]
        actual_shipping_fee = expenss["actual_shipping_fee"]
        shopee_shipping_rebate = expenss["shopee_shipping_rebate"]
        original_shopee_discount = expenss["original_shopee_discount"]
        
        ordershipping = abs(actual_shipping_fee)-abs(shopee_shipping_rebate)-abs(buyer_paid_shipping_fee)
        
        postiveor = abs(buyer_paid_shipping_fee)-abs(actual_shipping_fee)
        ordershipping = abs (ordershipping)
        first = grand_total - discount_from_voucher_seller
        subtotal = grand_total-service_charges
        f_total = grand_total+(ordershipping)-(service_charges)
        service_fee = first - ordershipping
        service_fee = first + ordershipping - f_total

        service_charges = service_charges - original_shopee_discount
        service_charges = service_charges+expenss.get('order_ams_commission_fee', 0)
        

        
        
        shopping_f = expenss["shopee_shipping_rebate"] +  expenss["buyer_paid_shipping_fee"] - expenss["actual_shipping_fee"]

    

        if shopping_f > 0:
            shopping_f = -shopping_f  # Convert positive to negative
        elif shopping_f < 0:
            shopping_f = abs(shopping_f)  # Convert negative to positive        

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
                "rate" : service_charges,
                "qty": 1
            })
            
            if shopping_f:
                new_invoice.append("items", {
                    "item_code": "1234",
                    "item_name": "Total Delivery Fee",
                    "rate" : shopping_f,
                    "qty": 1
                })
            
            
            if shopping_f >= 0:
                new_invoice.disable_rounded_total = 1
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
            if sales_invoice:
                doc = get_payment_entry("Sales Invoice", sales_invoice.name)
                olddate = datetime.now()
                olddate_str = olddate.strftime("%Y-%m-%d")
                doc.reference_no = ordersn
                doc.reference_date = olddate_str
                doc.mode_of_payment = "Shopee Fee"
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                #doc.submit()
                return doc
        except frappe.DoesNotExistError:
            pass
        except frappe.DuplicateEntryError:
            return sales_invoice


    def create_sales_invoice(self, sale_order):
        doc = make_sales_invoice(sale_order,ignore_permissions=True)
        doc.custom_channel = "Shopee"
        doc.additional_discount_account = "4170-00 SALES DISCOUNT"
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

    def create_pick_list(self,sale_order):
        sales_order = frappe.get_doc("Sales Order", sale_order)
        unavailable_items = []
        for item in sales_order.items:
            required_qty = item.qty
            available_qty = item.actual_qty
            
            if available_qty < required_qty:
                unavailable_items.append({
                    "item_code": item.item_code,
                    "required_qty": required_qty,
                    "available_qty": available_qty
                })
        if not unavailable_items:
            doc = create_pick_list(sale_order)
            doc.submit()
            frappe.db.commit()

        return unavailable_items

    
    
    
    def get_bundle_deal_info(self,item):
         
        return item
        
        partner_id = int(2004610)
        partner_key = "da22ac428afd591add1e4a988eaff7b7981d66980b19323d7d5a5c19116e575a"
        shop_id = int(213497319)

        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_value('access_token')
        kwargs = {
            'item_id_list': item["item_id"]
        }
        shopee  = Client(shop_id, partner_id, partner_key, accesstoken)
        shopee.set_access_token(accesstoken)
        shopee  = shopee.execute('product/get_item_promotion', "GET", kwargs)
        pormotionid = shopee["response"]["success_list"][0]["promotion"]
        return pormotionid
        
        return item
    
    
    def create_sales_order(self, ordersn,order, customer_key, expense):
        
        if frappe.db.exists("Sales Order", {"marketplace_order_number": order['order_sn']}):
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": ordersn})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Sales Order')
            new_order.customer = customer_key

            current_date = datetime.now().date()
            delivery_date = current_date + timedelta(days=2)
            new_order.delivery_date = delivery_date


            new_order.marketplace_order_number = order.get('order_sn', '')

            coin = expenss.get('coins', 0)

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
                    
                
                if item.get("discounted_price"):
                    pprice = item.get("discounted_price") / item.get("quantity_purchased",1)  
                   
                pprice = round(pprice,2)
                
                if item.get("promotion_type"):
                    promotion_type = item.get("promotion_type") 
                
                
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
                
                
            if expense.get('voucher_from_seller', 0):
                new_order.append("custom_seller_voucher",{
                    "doctype": 'Seller Voucher List',
                    "voucher_name": 'Seller Discount',
                    "voucher_amount": expense.get('voucher_from_seller', 0)
                })
                new_order.discount_amount = expense.get('voucher_from_seller', 0)
                
            if expense.get('voucher_from_shopee', 0):
                new_order.custom_marketplace_discount = expense.get('voucher_from_shopee', 0)
                
                
            new_order.custom_marketplace_taxes_and_charges = float(expenss.get('buyer_paid_shipping_fee', 0))
                
            new_order.custom_grand_total_marketplace = order.get('total_amount', '')
                
            for item in taxs:
                new_order.append("taxes",item)

            new_order.disable_rounded_total = 1
            new_order.taxes_and_charges = 'Thailand Tax - Clinton'
            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Shopee"
            new_order.selling_price_list = "Shopee"
            try:
                new_order.insert(ignore_permissions=True)
                new_order.submit()
                frappe.db.commit()
                return new_order.name
            except frappe.DuplicateEntryError:
                return None


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
                # bins = frappe.get_all('Bin', filters={'item_code': sku}, fields=['actual_qty'])
                # if bins:
                return 1
                # else:
                #     return 0
    

    def inser_customer(self, order, buyer_id):
        
        address_data = order["recipient_address"]
        name = address_data['name']
        if name == "****":
            name = order["buyer_username"]


        try:
            existing_customer = frappe.get_doc("Customer", {"customer_name": "SH-"+str(buyer_id)})
            return existing_customer.name
        except frappe.DoesNotExistError:
            customer = frappe.get_doc({
                "doctype": "Customer",
                "name": "SH-"+str(buyer_id),
                "customer_name": "SH-"+str(buyer_id),
                "full_name": str(name),
                "customer_group": "Shopee",
                "territory": "Thailand",
                "marketplace_buyer_id": buyer_id
            })
            customer.insert(ignore_permissions=True)
            frappe.db.commit()
            return customer.name

    def create_contact_for_customer(self,customer, order):
        address_data = order["recipient_address"]
        name = address_data['name']


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
def handle_delay_event_lazada(ordersn,shop_id,status,buyer_id,log_name):
    frappe.logger().info(f"Handling completed order: {ordersn}")
    connect = LazadaMarketplaceClient()	
    return connect.handle_lazada_order_status ( ordersn,shop_id,status,buyer_id,log_name)

@frappe.whitelist(allow_guest=True)
def push_shopee_lazada(ordersn,shop_id,status,buyer_id):
    if status.lower() != 'delivered':
        try:
            contact = frappe.new_doc("Marketplace Logs")
            contact.order_id = ordersn
            contact.status = status
            contact.shope_id = shop_id
            contact.buyer_id = buyer_id
            contact.marketplace = "Lazada"
            contact.custom_job_completed = 1
            contact.insert(ignore_permissions=True)
            connect = LazadaMarketplaceClient()	
            return connect.handle_lazada_order_status ( ordersn,shop_id,status,buyer_id,contact.name)
        except Exception:
            pass
    else:
        contact = frappe.new_doc("Marketplace Logs")
        contact.order_id = ordersn
        contact.status = status
        contact.shope_id = shop_id
        contact.buyer_id = buyer_id
        contact.marketplace = "Lazada"
        contact.custom_job_completed = 0
        contact.insert(ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def feach_lazada_orders(pageno):
    frappe.set_user("Administrator")  
    time_from = datetime(2024, 4, 1).timestamp()
    time_to = datetime(2024, 4, 15).timestamp()

    from_datetime = datetime.fromtimestamp(time_from)
    to_datetime = datetime.fromtimestamp(time_to)

    # Convert datetime objects to ISO 8601 format
    iso_from = from_datetime.isoformat()
    iso_to = to_datetime.isoformat()
     
    docSettings = frappe.get_single("Marketplace integration")
    accesstoken = docSettings.get_password('lazada_access_token')
    client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
    request = LazopRequest('/orders/get','GET')
    request.add_api_param('created_after', iso_from)
    request.add_api_param('limit', 100)
    request.add_api_param('offset', pageno)
    order_details = client.execute(request, accesstoken).body


    order_details = order_details['data']['orders']
    results = []
    if order_details:
            for order in order_details:
                ordersn = order["order_id"]
                #doc_list = frappe.get_list('Payment Entry', {'reference_no': ordersn})
                #for doc in doc_list:
                #    frappe.db.delete('Payment Entry', doc["name"])
                results.append(ordersn)

    return results
    #@connect = LazadaMarketplaceClient()	
    #return connect.handle_orders_list ( order_details["data"]["orders"])



@frappe.whitelist(allow_guest=True)
def feach_lazada_order(**kwargs):
    connect = LazadaMarketplaceClient()
    orderno = kwargs["order"]
    if ',' in kwargs["order"]:
        order_numbers = orderno.split(',') 
        results = []
        for order_number in order_numbers:
            result = connect.handle_orders_s(order_number.strip()) 
            results.append(result)

        return results
    else:
        return connect.handle_orders_s(orderno.strip())
        connect = LazadaMarketplaceClient()	
        return connect.handle_lazada_order_status ( ordersn,shop_id,status,buyer_id,contact.name)
    except Exception:
        pass

class LazadaMarketplaceClient:
    def handle_orders_s(self,orderno):
        frappe.set_user("Administrator")  
        frappe.flags.mute_messages = True

        # order_info = self.get_order_info(orderno)
        # order_items = json.loads(order_info.get('order_items', '[]'))
        # order_items = order_items.get('data', '[]')

        # buyer_id = order_items[0].get('buyer_id', '')
        # status = order_items[0].get('status', '')

        # if status == "canceled":
        doc_list = frappe.get_list('Sales Order', {'marketplace_order_number': orderno})
        for doc in doc_list:
            frappe.db.delete('Sales Order', doc["name"])
            #frappe.delete_doc('Sales Order', doc["name"])


        return
        


        

        return

        self.create_payment_entry(orderno)
        self.create_purchase_invoice_lazada(orderno)
        return
        #$self.create_payment_entry(orderno)
        #order_info = self.get_order_info(orderno)
        #order_details_json = json.loads(order_info.get('order_details', '[]'))
        #order_items = json.loads(order_info.get('order_items', '[]'))
        #order_details = order_details_json.get('data', '[]')
        #order_items = order_items.get('data', '[]')

        #product = self.check_product_sku(order_items)
        
        return self.create_purchase_invoice_lazada(orderno)


        #
        return
        try:
            frappe.flags.mute_messages = True
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": orderno})
            return existing_doc.name
        except frappe.DoesNotExistError:
            frappe.flags.mute_messages = True
            ordersn = orderno

            order_info = self.get_order_info(ordersn)
            order_details_json = json.loads(order_info.get('order_details', '[]'))
            order_items = json.loads(order_info.get('order_items', '[]'))
            order_details = order_details_json.get('data', '[]')
            order_items = order_items.get('data', '[]')
            


            buyer_id = order_items[0].get('buyer_id', '')
            status = order_items[0].get('status', '')
            customer_key = self.inser_customer(order_details,buyer_id)
            frappe.set_user("Administrator")  
            sale_order = self.create_sales_order(order_details,order_items,customer_key)
            return sale_order


            if not frappe.db.exists("Marketplace Logs", {"order_id": ordersn}):
                order_info = self.get_order_info(ordersn)
                order_details_json = json.loads(order_info.get('order_details', '[]'))
                order_items = json.loads(order_info.get('order_items', '[]'))
                order_details = order_details_json.get('data', '[]')
                order_items = order_items.get('data', '[]')


                buyer_id = order_items[0].get('buyer_id', '')
                status = order_items[0].get('status', '')


                customer_key = self.inser_customer(order_details,buyer_id)
                product = self.check_product_sku(order_items)

                contact = frappe.new_doc("Marketplace Logs")
                contact.order_id = ordersn
                contact.status = status
                contact.buyer_id = buyer_id
                contact.marketplace = "Lazada"
                contact.insert(ignore_permissions=True)
                log_name = contact.name


                if product:
                    # Create a new document only if it doesn't already exist
                    frappe.set_user("Administrator")  
                    sale_order = self.create_sales_order(order_details,order_items,customer_key)
                    if sale_order:
                        frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
                    if status.lower() == 'pending':
                        self.create_pack_list(sale_order)
                    elif  status.lower() == 'ready_to_ship':
                        self.create_pack_list(sale_order)
                        self.create_delivery_note(sale_order,ordersn)
                        self.create_sales_invoice(sale_order)   
                    elif  status.lower() == 'delivered':
                        self.create_pack_list(sale_order)
                        self.create_delivery_note(sale_order,ordersn)
                        self.create_sales_invoice(sale_order)   
                        self.create_payment_entry(ordersn)
                        self.create_purchase_invoice_lazada(ordersn,order_details,order_items)
                    elif  status.lower() == 'confirmed':
                        self.create_pack_list(sale_order)
                        self.create_delivery_note(sale_order,ordersn)
                        self.create_sales_invoice(sale_order)   
                        self.create_payment_entry(ordersn)
                        self.create_purchase_invoice_lazada(ordersn,order_details,order_items)
                    elif  status.lower() == 'shipped':
                        self.create_pack_list(sale_order)
                        self.create_delivery_note(sale_order,ordersn)
                        self.create_sales_invoice(sale_order)   
                        self.create_payment_entry(ordersn)
                        self.create_purchase_invoice_lazada(ordersn,order_details,order_items)
                else:
                    order_issue = self.create_order_issue(order_details,order_items,customer_key)
                    if order_issue:
                        frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)

    def handle_orders_list(self,orders):
        if orders:
            for order in orders:
                ordersn = order["order_id"]
                order_info = self.get_order_info(ordersn)

                if order_info:
                    order_details_json = json.loads(order_info.get('order_details', '[]'))
                    order_items = json.loads(order_info.get('order_items', '[]'))
                    order_details = order_details_json.get('data', '[]')
                    order_items = order_items.get('data', '[]')


                    buyer_id = order_items[0].get('buyer_id', '')
                    status = order_items[0].get('status', '')


                    product = self.check_product_sku(order_items)
                    

                    if not frappe.db.exists("Marketplace Logs", {"order_id": ordersn}):
                        contact = frappe.new_doc("Marketplace Logs")
                        contact.order_id = ordersn
                        contact.status = status
                        contact.buyer_id = buyer_id
                        contact.marketplace = "Lazada"
                        contact.insert(ignore_permissions=True)
                        log_name = contact.name

                        customer_key = self.inser_customer(order_details,buyer_id)
                    
                        if customer_key:
                            frappe.db.set_value('Marketplace Logs', log_name, 'custom_customer', customer_key)

                        if product:
                            # Create a new document only if it doesn't already exist
                            frappe.set_user("Administrator")  
                            sale_order = self.create_sales_order(order_details,order_items,customer_key)
                            sale_order_status = frappe.db.get_value("Sales Order", sale_order , ["status"])
                            
                            if sale_order:
                                frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)

                                if status.lower() == 'pending':
                                    self.create_pack_list(sale_order)
                                elif  status.lower() == 'ready_to_ship':
                                    self.create_pack_list(sale_order)
                                    self.create_delivery_note(sale_order,ordersn)
                                    self.create_sales_invoice(sale_order)   
                                elif  status.lower() == 'delivered':
                                    if sale_order_status == "Completed": 
                                        self.create_pack_list(sale_order)
                                        self.create_delivery_note(sale_order,ordersn)
                                        self.create_sales_invoice(sale_order)   
                                        self.create_payment_entry(ordersn)
                                        self.create_purchase_invoice_lazada(ordersn)
                                elif  status.lower() == 'confirmed':
                                    if sale_order_status == "Completed": 
                                        self.create_pack_list(sale_order)
                                        self.create_delivery_note(sale_order,ordersn)
                                        self.create_sales_invoice(sale_order)   
                                        self.create_payment_entry(ordersn)
                                        self.create_purchase_invoice_lazada(ordersn)
                        else:
                            order_issue = self.create_order_issue(order_details,order_items,customer_key)
                            if order_issue:
                                frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)




    def handle_lazada_order_status( self, ordersn,shop_id,status,buyer_id,log_name):
        order_info =  self.get_order_info(ordersn)
        if order_info:
            
            order_details_json = json.loads(order_info.get('order_details', '[]'))
            order_items = json.loads(order_info.get('order_items', '[]'))
            order_details = order_details_json.get('data', '[]')
            order_items = order_items.get('data', '[]')

            customer_key = self.inser_customer(order_details,buyer_id)
            if customer_key:
                frappe.db.set_value('Marketplace Logs', log_name, 'custom_customer', customer_key)


            product = self.check_product_sku(order_items)
            if product:
                frappe.set_user("Administrator")  
                
                sale_order = self.create_sales_order(order_details,order_items,customer_key)
                if status.lower() == 'unpaid':
                    frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order)
                else:
                    if frappe.db.exists("Sales Order", {"marketplace_order_number": ordersn}):
                        sale_order = frappe.get_doc("Sales Order", {"marketplace_order_number": ordersn})
                        frappe.db.set_value('Marketplace Logs', log_name, 'sale_order', sale_order.name)
                        sale_order_status = frappe.db.get_value("Sales Order", sale_order.name , ["status"])
                        if status.lower() == 'pending':
                            unavailable_items = self.create_pick_list(sales_order.name)
                            if unavailable_items:
                                create_marketplace_log("Lazada", ordersn, "pending", shop_id, buyer_id, unavailable_items)
                        elif  status.lower() == 'ready_to_ship':
                            self.create_delivery_note(sale_order.name,ordersn)
                            self.create_sales_invoice(sale_order.name)   
                        elif  status.lower() == 'delivered':
                            if sale_order_status == "Completed":    
                                self.create_payment_entry(ordersn)
                                #self.create_purchase_invoice_lazada(ordersn)

            else:
                order_issue = self.create_order_issue(order_details,order_items,customer_key)
                if order_issue:
                    frappe.db.set_value('Marketplace Logs', log_name, 'custom_sale_order_issue', order_issue)

    def create_purchase_invoice_lazada(self, ordersn):
        
        try:
             existing_doc = frappe.get_doc("Purchase Invoice", {"marketplace_order_number": ordersn})
             return existing_doc.name
        except frappe.DoesNotExistError:

            expenss = self.getorderdetails_addional_expenss(ordersn)
            order_info = self.get_order_info(ordersn)
            order_details_json = json.loads(order_info.get('order_details', '[]'))
            order_items = json.loads(order_info.get('order_items', '[]'))
            order_details = order_details_json.get('data', '[]')
            order_items = order_items.get('data', '[]')
            grand_total = 0
            subside = 0


            seller_voucher_total = 0
            item_price_total = 0
            for item in order_items:
                amount_str = item.get('item_price', '0')
                item_price_total += float(amount_str)

                if item.get('voucher_seller', '0'):
                    amount_str = item.get('voucher_seller', '0')
                    seller_voucher_total += float(amount_str)

            sakes_order_grand_total = round(item_price_total - seller_voucher_total, 2)
                

            for item in expenss:
                amount_str = item.get('amount', '0').replace(',', '')
                grand_total += float(amount_str)
                if item.get('fee_type', 0) == "1028":
                    subside += float(item.get('amount', 0))
            grand_total = round(grand_total,2)

            services_fee =  abs(grand_total) - abs(sakes_order_grand_total)
            after_subside = services_fee - subside

            subside = abs(subside)
            subtotal = float(order_details['price']) - order_details['voucher']
            total = abs(subtotal) - abs(grand_total)

            

            total_fee = abs(round(after_subside, 2))

            new_invoice = frappe.new_doc('Purchase Invoice')
            new_invoice.supplier = "Lazada Co., Ltd",
            
            new_invoice.owner_department = "API Admin - Clinton"
            new_invoice.marketplace_order_number = ordersn
            new_invoice.append("items", {
                "item_code": "1234",
                "item_name": "Total Fees and Service Charges",
                "rate" : total_fee,
                "qty": 1
            })

            if subside:
                new_invoice.append("items", {
                    "item_code": "1234",
                    "item_name": "Total Delivery Fee",
                    "rate" : subside,
                    "qty": 1
                })
            new_invoice.disable_rounded_total = 1
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
            existing_entries =frappe.get_list("Payment Entry", filters={"reference_doctype": "Sales Invoice", "reference_name": sales_invoice.name})
            if existing_entries:
                # If payment entry exists, return None or any appropriate value
                return None
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
        doc.additional_discount_account = "4170-00 SALES DISCOUNT"
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
    def create_pick_list(self, sale_order):
        sales_order = frappe.get_doc("Sales Order", sale_order)
        unavailable_items = []
        for item in sales_order.items:
            required_qty = item.qty
            available_qty = item.actual_qty
            
            if available_qty < required_qty:
                unavailable_items.append({
                    "item_code": item.item_code,
                    "required_qty": required_qty,
                    "available_qty": available_qty
                })
        if not unavailable_items:
            doc = create_pick_list(sale_order)
            doc.save(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()
        return unavailable_items
    
    def create_sales_order(self, order_details, order_items, customkey):

        
        if frappe.db.exists("Sales Order", {"marketplace_order_number": order_details['order_number']}):
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": order_details['order_number']})
            return existing_doc.name
        else:
            new_order = frappe.new_doc('Sales Order')
            new_order.customer = customkey
            current_date = datetime.now().date()
            delivery_date = current_date + timedelta(days=2)
            new_order.delivery_date = delivery_date
            new_order.marketplace_order_number = order_details.get('order_number', '')
            platform_voucher = 0
            seller_voucher = 0
            discounttotal = 0
            #$totalz = $order["price"]+$shipping_price;
            taxs = self.get_listof_taxs()
            item_price = item.get('item_price')
            paid_price = item.ge("paid_price")
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
                new_order.discount_amount = seller_voucher
            for item in taxs:
                new_order.append("taxes",item)
            new_order.disable_rounded_total = 1
            if platform_voucher:
                new_order.custom_marketplace_discount = platform_voucher
            new_order.custom_grand_total_marketplace = grand_total_marketplace
            new_order.custom_marketplace_taxes_and_charges = float(order_details["shipping_fee"])
            new_order.taxes_and_charges = 'Thailand Tax - Clinton'



            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Lazada"
            new_order.selling_price_list = "Lazada"
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
                    "item":  self.truncate_string(item['name'], 20),
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
        
    def truncate_string(self,text, max_length):
        if len(text) <= max_length:
            return text
        else:
            return text[:max_length]
    

    def check_product_sku(self, order_info):
        for item in order_info:
            sku = item["sku"]
            exists = frappe.db.exists("Item", sku, cache=False)
            if not exists:
                return 0
            else:
                # bins = frappe.get_all('Bin', filters={'item_code': sku}, fields=['actual_qty'])
                # if bins:
                return 1
                # else:
                #     return 0

    def inser_customer(self, order_details, buyer_id):
        customer_info = order_details['address_shipping'] 
        name = customer_info["first_name"] + customer_info["last_name"]


        try:
            existing_customer = frappe.get_doc("Customer", {"marketplace_buyer_id": buyer_id})
            return existing_customer.name
        except frappe.DoesNotExistError:
            customer = frappe.get_doc({
                "doctype": "Customer",
                "full_name": str(name),
                "customer_name": "LAZ-"+str(buyer_id),
                "customer_group": "Lazada",
                "territory": "Thailand",
                "marketplace_buyer_id": buyer_id
            })
            customer.insert(
                ignore_permissions=True
            )
            frappe.db.commit()
            #self.create_contact_for_customer(customer.name, customer_info)
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


        address = frappe.get_doc({
            "doctype": "Address",
            "address_line1": customer_info["address1"] +" "+customer_info["address2"]+" "+customer_info["address3"]+" "+customer_info["address4"]+" "+customer_info["address5"],
            "phone": customer_info["phone"],
            "address_type": "Shipping",
            "city": "-",
        })
        address.append('links', {
                'link_doctype': 'Customer',
                'link_name': customer
        })
        address.insert(ignore_permissions=True)
        frappe.db.commit()
    
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
