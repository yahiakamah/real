# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class FacilityServiceCategory(models.Model):
    _name = 'facility.service.category'
    _description = 'Facility Service Category'
    _order = 'sequence, name'

    name = fields.Char('Category', required=True, translate=True)
    code = fields.Char('Code')
    sequence = fields.Integer('Sequence', default=10)
    color = fields.Integer('Color')
    active = fields.Boolean('Active', default=True)
    response_time_hours = fields.Float(
        'SLA Response Time (Hours)',
        default=24.0,
        help='Default number of hours allowed to resolve a work order in this category, '
             'used to compute the SLA deadline.')
    default_priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Default Priority', default='1')
    work_order_ids = fields.One2many('facility.work.order', 'category_id', string='Work Orders')
    work_order_count = fields.Integer('Work Order Count', compute='_compute_work_order_count')

    _sql_constraints = [
        ('unique_category_code', 'UNIQUE (code)', 'Service category code must be unique!'),
    ]

    @api.depends('work_order_ids')
    def _compute_work_order_count(self):
        for category in self:
            category.work_order_count = len(category.work_order_ids)

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            'name': _('Work Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.work.order',
            'view_mode': 'list,kanban,form,calendar',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }
