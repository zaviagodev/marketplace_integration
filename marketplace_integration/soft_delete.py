import frappe

def todo_query():
    return "(`tabMarketplace order Issue`.status = 'Open' )"


@frappe.whitelist()
def deltedoc(docname):
    frappe.db.set_value("Marketplace order Issue",docname,"status","Deleted")
