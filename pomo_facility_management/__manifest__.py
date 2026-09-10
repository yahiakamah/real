# -*- coding: utf-8 -*-
{
    'name': 'Facility Management',
    'version': '18.0.2.0.0',
    'category': 'Real Estate',
    'sequence': 15,
    'summary': 'Professional facility & maintenance management for real estate properties',
    'description': """
Pomo Facility Management
=========================
Enterprise-grade facility and maintenance operations integrated with Real Estate Development:

**Operations**
- Work orders (corrective, preventive, inspection, installation)
- Tenant maintenance requests with auto work-order creation
- Property inspections with customizable checklists
- SLA tracking and overdue alerts

**Asset Management**
- Asset registry per building / unit (elevators, HVAC, pumps, generators, ...)
- Equipment lifecycle tracking with warranty management
- Preventive maintenance scheduling

**Vendor Management**
- Maintenance vendor contracts
- Contract expiry tracking and auto-expiry
- Scope of work documentation

**Integration with Real Estate Development**
- Full project → building → unit hierarchy
- Pull project and unit data from pomo_real_estate
- Cross-module navigation and reporting

**Configuration**
- Service categories with SLA response times
- Reusable inspection checklist templates
- Flexible security groups (Requester / Technician / Manager)
    """,
    'author': 'Ahmed Yahia',
    'website': '',
    'depends': ['base', 'mail', 'pomo_real_estate', 'project'],
    'data': [
        'security/facility_security.xml',
        'security/ir.model.access.csv',

        'data/facility_sequence_data.xml',
        'data/facility_new_sequences.xml',
        'data/facility_category_data.xml',
        'data/facility_cron_data.xml',

        'views/facility_service_category_views.xml',
        'views/facility_asset_views.xml',
        'views/facility_work_order_views.xml',
        'views/facility_maintenance_plan_views.xml',
        'views/facility_inspection_views.xml',
        'views/facility_vendor_contract_views.xml',
        'views/facility_tenant_request_views.xml',
        'views/facility_checklist_template_views.xml',
        'views/facility_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'AGPL-3',
}
