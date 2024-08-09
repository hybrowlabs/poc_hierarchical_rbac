import sys

import frappe
from frappe.core.page.permission_manager.permission_manager import get_permissions


def add_custom_fields():
    doctypes = frappe.db.get_all("DocType", {"istable": 0, "issingle": 0})
    count = 0
    loading = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    loading.reverse()
    # insert a custom field in every doctype
    for doctype in doctypes:
        if not frappe.db.exists("Custom Field", {"dt": doctype["name"], "fieldname": "cn_team"}) and doctype[
            "name"] not in ["DocType", "Module Def"]:
            doc = frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": doctype["name"],
                    "module": "Meril",
                    "fieldname": "cn_team",
                    "label": "CN Team",
                    "fieldtype": "Link",
                    "options": "CN Team",
                    "hidden": 1,
                    "read_only": 1
                }
            )
            doc.insert(ignore_permissions=True)
        count += 1
        sys.stdout.write(f'\r{loading[count % 8]} Added {count} custom fields to {len(doctypes)} doctypes')
        sys.stdout.flush()
    print()


def after_app_install(_app_name):
    add_custom_fields()


def after_doc_insert(_doc, _method):
    add_custom_fields()


def after_insert(doc, _method):
    if frappe.db.exists("Employee", {
        "user_id": frappe.session.user
    }) and frappe.session.user == doc.owner:
        employee = frappe.get_doc("Employee", frappe.db.exists("Employee", {
            "user_id": frappe.session.user
        }))
        cn_team_ = frappe.db.exists("CN Team", {
            "manager": employee.name
        })
        if doc.__class__.__name__ != "CN Team" and doc.cn_team is None and cn_team_:
            cn_team = frappe.get_doc("CN Team", frappe.db.exists("CN Team", {
                "manager": employee.name
            }))
            doc.cn_team = cn_team.name
            doc.save(ignore_permissions=True)


def on_employee_insert(doc, _method):
    # add condition for root node
    cn_teams = frappe.get_all("CN Team")
    print(cn_teams)
    if len(cn_teams) == 0 and doc.reports_to is None:
        new_team = frappe.new_doc("CN Team")
        new_team.manager = doc.name
        new_team.is_group = 1
        new_team.insert(ignore_permissions=True)
        return
    elif doc.reports_to is None:
        frappe.throw("Reports to cannot be empty")

    if doc.cn_team is None:
        parent_team_name = frappe.db.exists("CN Team", {
            "manager": doc.reports_to
        })
        parent_team = frappe.get_doc("CN Team", parent_team_name)
        if parent_team.is_group != 1:
            parent_team.is_group = 1
            parent_team.save(ignore_permissions=True)

        doc.cn_team = parent_team_name
        new_team = frappe.new_doc("CN Team")
        new_team.manager = doc.name
        new_team.parent_cn_team = parent_team_name
        new_team.doctypes = parent_team.doctypes
        new_team.insert(ignore_permissions=True)
        doc.save(ignore_permissions=True)


def on_employee_update(doc, _method):
    parent_team = frappe.db.exists("CN Team", {
        "manager": doc.reports_to
    })
    current_team = frappe.get_doc("CN Team", frappe.db.exists("CN Team", {
        "manager": doc.name
    }))
    if parent_team != current_team.parent_cn_team:
        current_team.parent_cn_team = parent_team
        current_team.save(ignore_permissions=True)


def create_permissions(user, team, apply_to_all, doctypes):
    permissions = frappe.get_list("User Permission", {
        "user": user,
        "allow": "CN Team",
        "for_value": team
    })
    # delete all the before permissions
    for permission in permissions:
        frappe.db.delete("User Permission", permission)

    if apply_to_all:
        if not frappe.db.exists("User Permission", {
            "user": user,
            "allow": "CN Team",
            "for_value": team,
            "apply_to_all_doctypes": 1
        }):
            user_permission = frappe.new_doc("User Permission")
            user_permission.user = user
            user_permission.allow = "CN Team"
            user_permission.for_value = team
            user_permission.apply_to_all_doctypes = 1
            user_permission.save(ignore_permissions=True)
    else:
        for doctype in doctypes:
            user_permission = frappe.new_doc("User Permission")
            user_permission.user = user
            user_permission.allow = "CN Team"
            user_permission.for_value = team
            user_permission.apply_to_doctype = 0
            user_permission.applicable_for = doctype
            user_permission.save(ignore_permissions=True)


# def on_team_validate(doc, _method):
#     if doc.role_profile and len(doc.doctypes) > 0:
#         role_profile_doc = frappe.get_doc("Role Profile", doc.role_profile)
#         for doctype_child in doc.doctypes:
#             doctype = doctype_child.doctype_selected
#             for role_doc in role_profile_doc.roles:
#                 role = role_doc.role
#                 for permission in get_permissions(doctype, role):
#                     if permission.get("if_owner") != 1:
#                         frappe.throw(f"Please add Creator Only permissions for role {role} in doctype {doctype}")


def on_team_update(doc, _method):
    doctypes = [doctype.doctype_selected for doctype in doc.doctypes]
    parent_cn_team = None
    parent_doctypes = []
    if doc.parent_cn_team is not None:
        parent_cn_team = frappe.get_doc("CN Team", doc.parent_cn_team)
        parent_doctypes = [doctype.doctype_selected for doctype in parent_cn_team.doctypes]
    user = frappe.get_doc("Employee", frappe.db.exists("Employee", doc.manager)).user_id
    if user:
        create_permissions(user, doc.name, len(doc.doctypes) <= 0,
                           doctypes)
    if parent_cn_team:
        for doctype in doctypes:
            # check if this doctype is in parent cn team
            if doctype not in parent_doctypes:
                frappe.throw("Please add {0} to parent team {1}".format(doctype, doc.parent_cn_team))
