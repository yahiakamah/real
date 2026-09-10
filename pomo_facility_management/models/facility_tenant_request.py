# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class FacilityTenantRequest(models.Model):
    _name = 'facility.tenant.request'
    _description = 'Tenant Maintenance Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    # ─── Tenant ──────────────────────────────────────────────────────
    tenant_id = fields.Many2one(
        'res.partner', string='Tenant / Resident',
        required=True, tracking=True)
    tenant_phone = fields.Char(
        related='tenant_id.phone', string='Phone', readonly=True)
    tenant_email = fields.Char(
        related='tenant_id.email', string='Email', readonly=True)

    # ─── Location ────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'project.project', string='Project', tracking=True)
    building_id = fields.Many2one(
        'building', string='Building', required=True, tracking=True,
        domain="[('project_id', '=', project_id)]")
    unit_id = fields.Many2one(
        'product.template', string='Unit',
        domain="[('is_property', '=', True), ('building_id', '=', building_id)]",
        tracking=True)
    region_id = fields.Many2one(
        'regions', string='Region',
        related='building_id.region_id', store=True, readonly=True)

    # ─── Request Details ─────────────────────────────────────────────
    category_id = fields.Many2one(
        'facility.service.category', string='Service Category',
        required=True, tracking=True)
    description = fields.Text('Description', required=True)
    photo = fields.Image('Photo', max_width=1920, max_height=1920,
                          help='Attach a photo of the issue')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1', tracking=True)

    preferred_date = fields.Datetime('Preferred Service Date')

    # ─── State ───────────────────────────────────────────────────────
    state = fields.Selection([
        ('submitted', 'Submitted'),
        ('acknowledged', 'Acknowledged'),
        ('work_order_created', 'Work Order Created'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('rejected', 'Rejected'),
    ], string='Status', default='submitted', required=True, tracking=True,
        group_expand='_expand_states')

    # ─── Work Order Link ─────────────────────────────────────────────
    work_order_id = fields.Many2one(
        'facility.work.order', string='Work Order',
        readonly=True, copy=False)

    # ─── Feedback ────────────────────────────────────────────────────
    resolution_notes = fields.Text('Resolution Notes')
    satisfaction_rating = fields.Selection([
        ('1', '★'),
        ('2', '★★'),
        ('3', '★★★'),
        ('4', '★★★★'),
        ('5', '★★★★★'),
    ], string='Satisfaction Rating')

    @api.model
    def _expand_states(self, states, domain):
        return [key for key, _val in self._fields['state'].selection]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'facility.tenant.request') or 'New'
        return super().create(vals_list)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.building_id and self.building_id.project_id != self.project_id:
            self.building_id = False

    @api.onchange('building_id')
    def _onchange_building_id(self):
        if self.building_id and self.building_id.project_id:
            self.project_id = self.building_id.project_id
        if self.unit_id and self.unit_id.building_id != self.building_id:
            self.unit_id = False

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id and self.category_id.default_priority:
            self.priority = self.category_id.default_priority

    # ─── Actions ─────────────────────────────────────────────────────
    def action_acknowledge(self):
        self.write({'state': 'acknowledged'})

    def action_create_work_order(self):
        """Create a work order from this tenant request."""
        self.ensure_one()
        WorkOrder = self.env['facility.work.order']
        wo = WorkOrder.create({
            'building_id': self.building_id.id,
            'unit_id': self.unit_id.id if self.unit_id else False,
            'category_id': self.category_id.id,
            'work_type': 'corrective',
            'requested_by_id': self.tenant_id.id,
            'priority': self.priority,
            'description': self.description or '',
            'date_scheduled': self.preferred_date,
            'tenant_request_id': self.id,
        })
        self.write({
            'state': 'work_order_created',
            'work_order_id': wo.id,
        })
        return {
            'name': _('Work Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.work.order',
            'view_mode': 'form',
            'res_id': wo.id,
        }

    def action_resolve(self):
        self.write({'state': 'resolved'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_view_work_order(self):
        self.ensure_one()
        return {
            'name': _('Work Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.work.order',
            'view_mode': 'form',
            'res_id': self.work_order_id.id,
        }
