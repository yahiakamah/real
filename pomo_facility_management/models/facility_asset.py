# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class FacilityAsset(models.Model):
    _name = 'facility.asset'
    _description = 'Facility Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'building_id, name'

    name = fields.Char('Asset Name', required=True, tracking=True)
    code = fields.Char('Asset Code', copy=False, readonly=True, default='New')
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    category_id = fields.Many2one('facility.service.category', string='Service Category', tracking=True)
    asset_type = fields.Selection([
        ('equipment', 'Equipment'),
        ('infrastructure', 'Infrastructure'),
        ('safety', 'Safety System'),
    ], string='Asset Type', default='equipment', required=True)

    building_id = fields.Many2one('building', string='Building', required=True, tracking=True)
    unit_id = fields.Many2one(
        'product.template', string='Unit',
        domain="[('is_property', '=', True), ('building_id', '=', building_id)]",
        help='Leave empty for building-level assets (elevators, generators, common HVAC, ...).')
    project_id = fields.Many2one(
        'project.project', string='Project',
        related='building_id.project_id', store=True, readonly=True)
    region_id = fields.Many2one('regions', string='Region', related='building_id.region_id', store=True, readonly=True)
    location = fields.Char('Specific Location', help='e.g. Rooftop, Basement - Pump Room, Unit Kitchen')

    brand = fields.Char('Brand')
    model_number = fields.Char('Model Number')
    serial_number = fields.Char('Serial Number')
    supplier_id = fields.Many2one('res.partner', string='Supplier / Vendor')
    purchase_date = fields.Date('Purchase Date')
    warranty_end_date = fields.Date('Warranty End Date')
    in_warranty = fields.Boolean('Under Warranty', compute='_compute_in_warranty', store=True)

    state = fields.Selection([
        ('operational', 'Operational'),
        ('under_maintenance', 'Under Maintenance'),
        ('out_of_service', 'Out of Service'),
        ('decommissioned', 'Decommissioned'),
    ], string='Status', default='operational', tracking=True)

    maintenance_frequency_days = fields.Integer(
        'Preventive Maintenance Frequency (Days)', default=0,
        help='0 = no automatic preventive maintenance scheduling for this asset.')
    last_maintenance_date = fields.Date('Last Maintenance Date')
    next_maintenance_date = fields.Date('Next Maintenance Date', compute='_compute_next_maintenance_date', store=True)

    image_1920 = fields.Image('Photo', max_width=1920, max_height=1920)
    notes = fields.Text('Notes')

    work_order_ids = fields.One2many('facility.work.order', 'asset_id', string='Work Orders')
    work_order_count = fields.Integer('Work Order Count', compute='_compute_work_order_count')
    maintenance_plan_ids = fields.One2many('facility.maintenance.plan', 'asset_id', string='Maintenance Plans')

    _sql_constraints = [
        ('unique_asset_code', 'UNIQUE (code, company_id)', 'Asset code must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('facility.asset') or 'New'
        return super().create(vals_list)

    @api.depends('warranty_end_date')
    def _compute_in_warranty(self):
        today = fields.Date.context_today(self)
        for asset in self:
            asset.in_warranty = bool(asset.warranty_end_date and asset.warranty_end_date >= today)

    @api.depends('last_maintenance_date', 'maintenance_frequency_days')
    def _compute_next_maintenance_date(self):
        for asset in self:
            if asset.last_maintenance_date and asset.maintenance_frequency_days:
                asset.next_maintenance_date = asset.last_maintenance_date + relativedelta(
                    days=asset.maintenance_frequency_days)
            else:
                asset.next_maintenance_date = False

    @api.depends('work_order_ids')
    def _compute_work_order_count(self):
        for asset in self:
            asset.work_order_count = len(asset.work_order_ids)

    @api.onchange('building_id')
    def _onchange_building_id(self):
        if self.unit_id and self.unit_id.building_id != self.building_id:
            self.unit_id = False

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            'name': _('Work Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.work.order',
            'view_mode': 'list,kanban,form,calendar',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id, 'default_building_id': self.building_id.id},
        }
