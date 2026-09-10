# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class FacilityMaintenancePlan(models.Model):
    _name = 'facility.maintenance.plan'
    _description = 'Facility Preventive Maintenance Plan'
    _order = 'next_date'

    name = fields.Char('Plan Name', required=True)
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    asset_id = fields.Many2one('facility.asset', string='Asset', required=True, ondelete='cascade')
    building_id = fields.Many2one('building', string='Building', related='asset_id.building_id', store=True, readonly=True)
    project_id = fields.Many2one(
        'project.project', string='Project',
        related='building_id.project_id', store=True, readonly=True)
    category_id = fields.Many2one('facility.service.category', string='Service Category',
                                   related='asset_id.category_id', store=True, readonly=False)

    frequency_type = fields.Selection([
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], string='Frequency', default='months', required=True)
    interval = fields.Integer('Repeat Every', default=1, required=True)

    next_date = fields.Date('Next Due Date', required=True, default=fields.Date.context_today)
    last_generated_date = fields.Date('Last Generated On', readonly=True)

    technician_id = fields.Many2one('res.users', string='Default Technician')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1')
    description = fields.Text('Work Order Description')

    work_order_ids = fields.One2many('facility.work.order', 'maintenance_plan_id', string='Generated Work Orders')
    work_order_count = fields.Integer('Work Order Count', compute='_compute_work_order_count')

    @api.depends('work_order_ids')
    def _compute_work_order_count(self):
        for plan in self:
            plan.work_order_count = len(plan.work_order_ids)

    def _get_next_date(self, from_date):
        self.ensure_one()
        return from_date + relativedelta(**{self.frequency_type: self.interval})

    def _prepare_work_order_vals(self):
        self.ensure_one()
        return {
            'building_id': self.asset_id.building_id.id,
            'unit_id': self.asset_id.unit_id.id,
            'asset_id': self.asset_id.id,
            'category_id': self.category_id.id,
            'work_type': 'preventive',
            'assigned_technician_id': self.technician_id.id,
            'priority': self.priority,
            'description': self.description or self.name,
            'date_scheduled': self.next_date,
            'maintenance_plan_id': self.id,
        }

    def action_generate_work_order(self):
        WorkOrder = self.env['facility.work.order']
        created = self.env['facility.work.order']
        today = fields.Date.context_today(self)
        for plan in self:
            created |= WorkOrder.create(plan._prepare_work_order_vals())
            plan.write({
                'last_generated_date': today,
                'next_date': plan._get_next_date(plan.next_date),
            })
        return created

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            'name': _('Work Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.work.order',
            'view_mode': 'list,kanban,form,calendar',
            'domain': [('maintenance_plan_id', '=', self.id)],
        }

    @api.model
    def _cron_generate_preventive_work_orders(self):
        today = fields.Date.context_today(self)
        due_plans = self.search([('active', '=', True), ('next_date', '<=', today)])
        due_plans.action_generate_work_order()
