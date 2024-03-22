// Copyright (c) 2024, zaviago and contributors
// For license information, please see license.txt

frappe.ui.form.on("Marketplace integration", {
	start_shopee_connection:function(frm){
		var site = frappe.urllib.get_base_url();
		var requestData = {
			"client_site": site
		};
		$.ajax({
            type: "GET",
            url: "https://templete.zaviago.com/api/method/marketplace_management.auth.create_client.redirect_to_auth_shopee",
            contentType: "application/json",
			data: requestData,
            success: function(response) {
                if (response && response.message.url) {
					window.open(response.message.url,"_self");
                }
            },
            error: function(xhr, status, error) {
                frappe.msgprint("Error: " + error);
            }
        });
	},
	start_lazada_connection:function(frm){
		var site = frappe.urllib.get_base_url();
		var requestData = {
			"client_site": site
		};
		$.ajax({
            type: "GET",
            url: "https://templete.zaviago.com/api/method/marketplace_management.auth.create_client.redirect_to_auth_lazada",
            contentType: "application/json",
			data: requestData,
            success: function(response) {
                if (response && response.message.url) {
					window.open(response.message.url,"_self");
                }
            },
            error: function(xhr, status, error) {
                frappe.msgprint("Error: " + error);
            }
        });
	},
});
