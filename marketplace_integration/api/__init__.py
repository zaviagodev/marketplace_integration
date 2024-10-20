from marketplace_integration.marketplace.lazada_manager import lazada_manager
import frappe


@frappe.whitelist()
def get_product_skus(product_name):
    return lazada_manager.get_product_skus(product_name)
