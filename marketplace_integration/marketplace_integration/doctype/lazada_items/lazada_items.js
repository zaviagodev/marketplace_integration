// Copyright (c) 2024, zaviago and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lazada Items", {
	refresh(frm) {
        frappe.call({
            method: "marketplace_integration.api.get_product_skus",
            args: {
                "product_name": frm.doc.name
            },
            callback : function(r) {
                console.log(r.message)
                if(r.message) {
                    r.message.forEach(function(row) {
                        var child_row = frm.add_child("skus");
                        child_row.seller_sku = row.SellerSku;
                        child_row.shop_sku = row.ShopSku;
                        child_row.quantity = row.quantity;
                        child_row.price = row.price;
                        child_row.status = row.Status
                    });
                }
                frm.refresh_field("skus")
            }
    })
	},
});
