# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class FacilityWorkOrder(models.Model):
    _name = 'facility.work.order'
    _description = 'Facility Work Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, request_date desc'
    _rec_name = 'name'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency', store=True)

    building_id = fields.Many2one('building', string='Building', required=True, tracking=True)
    unit_id = fields.Many2one(
        'product.template', string='Unit',
        domain="[('is_property', '=', True), ('building_id', '=', building_id)]", tracking=True)
    project_id = fields.Many2one(
        'project.project', string='Project',
        related='building_id.project_id', store=True, readonly=True)
    region_id = fields.Many2one('regions', string='Region', related='building_id.region_id', store=True, readonly=True)
    asset_id = fields.Many2one(
        'facility.asset', string='Asset',
        domain="[('building_id', '=', building_id)]", tracking=True)

    category_id = fields.Many2one('facility.service.category', string='Service Category', required=True, tracking=True)
    work_type = fields.Selection([
        ('corrective', 'Corrective'),
        ('preventive', 'Preventive'),
        ('inspection', 'Inspection'),
        ('installation', 'Installation'),
    ], string='Work Type', default='corrective', required=True, tracking=True)
    maintenance_plan_id = fields.Many2one(
        'facility.maintenance.plan', string='Maintenance Plan', readonly=True, copy=False)
    tenant_request_id = fields.Many2one(
        'facility.tenant.request', string='Tenant Request', readonly=True, copy=False)

    requested_by_id = fields.Many2one(
        'res.partner', string='Requested By',
        default=lambda self: self.env.user.partner_id, tracking=True)
    assigned_technician_id = fields.Many2one('res.users', string='Assigned Technician', tracking=True)

    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1', tracking=True)

    description = fields.Text('Description', required=True)

    request_date = fields.Datetime('Request Date', default=fields.Datetime.now, readonly=True)
    date_scheduled = fields.Datetime('Scheduled Date')
    date_start = fields.Datetime('Start Date')
    date_end = fields.Datetime('End Date')
    duration_hours = fields.Float('Duration (Hours)', compute='_compute_duration_hours', store=True)

    sla_hours = fields.Float(related='category_id.response_time_hours', string='SLA (Hours)', store=True)
    sla_deadline = fields.Datetime('SLA Deadline', compute='_compute_sla_deadline', store=True)
    is_overdue = fields.Boolean('Overdue', compute='_compute_is_overdue', store=True)

    state = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='new', required=True, tracking=True, group_expand='_expand_states')

    material_line_ids = fields.One2many('facility.work.order.material', 'work_order_id', string='Materials Used')
    cost_estimate = fields.Monetary('Estimated Cost', currency_field='currency_id')
    cost_actual = fields.Monetary('Actual Cost', currency_field='currency_id', compute='_compute_cost_actual', store=True)

    closed_date = fields.Datetime('Closed Date', readonly=True, copy=False)
    feedback_rating = fields.Selection([
        ('1', 'Very Unsatisfied'),
        ('2', 'Unsatisfied'),
        ('3', 'Neutral'),
        ('4', 'Satisfied'),
        ('5', 'Very Satisfied'),
    ], string='Tenant Feedback')
    feedback_notes = fields.Text('Feedback Notes')

    @api.model
    def _expand_states(self, states, domain):
        return [key for key, _val in self._fields['state'].selection]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('facility.work.order') or 'New'
        return super().create(vals_list)

    @api.depends('date_start', 'date_end')
    def _compute_duration_hours(self):
        for order in self:
            if order.date_start and order.date_end and order.date_end > order.date_start:
                delta = order.date_end - order.date_start
                order.duration_hours = delta.total_seconds() / 3600.0
            else:
                order.duration_hours = 0.0

    @api.depends('request_date', 'sla_hours')
    def _compute_sla_deadline(self):
        for order in self:
            if order.request_date and order.sla_hours:
                order.sla_deadline = order.request_date + timedelta(hours=order.sla_hours)
            else:
                order.sla_deadline = False

    @api.depends('sla_deadline', 'state')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for order in self:
            order.is_overdue = bool(
                order.sla_deadline
                and order.state not in ('done', 'cancelled')
                and order.sla_deadline < now
            )

    @api.depends('material_line_ids.subtotal')
    def _compute_cost_actual(self):
        for order in self:
            order.cost_actual = sum(order.material_line_ids.mapped('subtotal'))

    @api.onchange('building_id')
    def _onchange_building_id(self):
        if self.unit_id and self.unit_id.building_id != self.building_id:
            self.unit_id = False
        if self.asset_id and self.asset_id.building_id != self.building_id:
            self.asset_id = False

    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        if self.unit_id:
            if self.unit_id.building_id:
                self.building_id = self.unit_id.building_id
            if self.unit_id.partner_id:
                self.requested_by_id = self.unit_id.partner_id

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and self.category_id.default_priority:
            self.priority = self.category_id.default_priority

    def action_assign(self):
        self.filtered(lambda o: o.state == 'new').write({'state': 'assigned'})

    def action_start(self):
        self.write({'state': 'in_progress', 'date_start': fields.Datetime.now()})

    def action_hold(self):
        self.write({'state': 'on_hold'})

    def action_resume(self):
        self.write({'state': 'in_progress'})

    def action_complete(self):
        self.write({'state': 'done', 'date_end': fields.Datetime.now(), 'closed_date': fields.Datetime.now()})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_new(self):
        self.write({'state': 'new', 'closed_date': False})


class FacilityWorkOrderMaterial(models.Model):
    _name = 'facility.work.order.material'
    _description = 'Facility Work Order Material Line'

    work_order_id = fields.Many2one('facility.work.order', string='Work Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product / Spare Part')
    description = fields.Char('Description')
    quantity = fields.Float('Quantity', default=1.0)
    unit_cost = fields.Float('Unit Cost', default=0.0)
    subtotal = fields.Monetary('Subtotal', compute='_compute_subtotal', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='work_order_id.currency_id', string='Currency', store=True)

    @api.depends('quantity', 'unit_cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.unit_cost = self.product_id.standard_price
