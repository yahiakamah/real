# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class FacilityVendorContract(models.Model):
    _name = 'facility.vendor.contract'
    _description = 'Facility Vendor / Maintenance Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end desc'
    _rec_name = 'name'

    name = fields.Char('Contract Name', required=True, tracking=True)
    code = fields.Char('Contract #', copy=False, readonly=True, default='New')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', store=True)

    # ─── Vendor ──────────────────────────────────────────────────────
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor / Contractor',
        required=True, tracking=True,
        domain="[('supplier_rank', '>', 0)]")
    vendor_phone = fields.Char(
        related='vendor_id.phone', string='Phone', readonly=True)
    vendor_email = fields.Char(
        related='vendor_id.email', string='Email', readonly=True)

    # ─── Scope ───────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'project.project', string='Project', tracking=True)
    building_id = fields.Many2one(
        'building', string='Building',
        domain="[('project_id', '=', project_id)]")
    category_ids = fields.Many2many(
        'facility.service.category', string='Service Categories')
    scope_of_work = fields.Html('Scope of Work')

    # ─── Contract Terms ──────────────────────────────────────────────
    date_start = fields.Date('Start Date', required=True, tracking=True)
    date_end = fields.Date('End Date', required=True, tracking=True)
    contract_value = fields.Monetary(
        'Contract Value', currency_field='currency_id')
    payment_terms = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annual', 'Semi-Annual'),
        ('annual', 'Annual'),
        ('lump_sum', 'Lump Sum'),
    ], string='Payment Terms', default='monthly')

    # ─── State ───────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)

    is_expired = fields.Boolean(
        'Expired', compute='_compute_is_expired', store=True)
    days_remaining = fields.Integer(
        'Days Remaining', compute='_compute_is_expired', store=True)

    # ─── Documents ───────────────────────────────────────────────────
    notes = fields.Text('Notes')

    # ─── Relations ───────────────────────────────────────────────────
    work_order_count = fields.Integer(
        'Work Orders', compute='_compute_work_order_count')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'facility.vendor.contract') or 'New'
        return super().create(vals_list)

    @api.depends('date_end', 'state')
    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for contract in self:
            if contract.date_end:
                contract.is_expired = (
                    contract.date_end < today
                    and contract.state not in ('cancelled',))
                delta = contract.date_end - today
                contract.days_remaining = max(delta.days, 0)
            else:
                contract.is_expired = False
                contract.days_remaining = 0

    def _compute_work_order_count(self):
        WorkOrder = self.env['facility.work.order']
        for contract in self:
            domain = [('building_id', '=', contract.building_id.id)]
            if contract.category_ids:
                domain.append(
                    ('category_id', 'in', contract.category_ids.ids))
            contract.work_order_count = WorkOrder.search_count(domain) \
                if contract.building_id else 0

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.building_id and self.building_id.project_id != self.project_id:
            self.building_id = False

    # ─── Actions ─────────────────────────────────────────────────────
    def action_activate(self):
        self.write({'state': 'active'})

    def action_expire(self):
        self.write({'state': 'expired'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_work_orders(self):
        self.ensure_one()
        domain = [('building_id', '=', self.building_id.id)]
        if self.category_ids:
            domain.append(('category_id', 'in', self.category_ids.ids))
        return {
            'name': _('Work Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.work.order',
            'view_mode': 'kanban,list,form',
            'domain': domain,
        }

    @api.model
    def _cron_check_contract_expiry(self):
        """Auto-expire contracts past their end date."""
        today = fields.Date.context_today(self)
        expired = self.search([
            ('state', '=', 'active'),
            ('date_end', '<', today),
        ])
        expired.write({'state': 'expired'})
