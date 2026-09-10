# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class FacilityInspection(models.Model):
    _name = 'facility.inspection'
    _description = 'Facility Inspection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_planned desc, name'
    _rec_name = 'name'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    # ─── Location ────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'project.project', string='Project', tracking=True)
    building_id = fields.Many2one(
        'building', string='Building', required=True, tracking=True,
        domain="[('project_id', '=', project_id)]")
    unit_id = fields.Many2one(
        'product.template', string='Unit',
        domain="[('is_property', '=', True), ('building_id', '=', building_id)]")
    region_id = fields.Many2one(
        'regions', string='Region',
        related='building_id.region_id', store=True, readonly=True)

    # ─── Classification ──────────────────────────────────────────────
    inspection_type = fields.Selection([
        ('routine', 'Routine Inspection'),
        ('pre_handover', 'Pre-Handover'),
        ('post_handover', 'Post-Handover'),
        ('annual', 'Annual Inspection'),
        ('complaint', 'Complaint Investigation'),
        ('safety', 'Safety Inspection'),
    ], string='Inspection Type', default='routine', required=True, tracking=True)

    # ─── People ──────────────────────────────────────────────────────
    inspector_id = fields.Many2one(
        'res.users', string='Inspector', required=True, tracking=True,
        default=lambda self: self.env.user)
    tenant_id = fields.Many2one(
        'res.partner', string='Tenant / Owner',
        help='The occupant or owner of the inspected unit')

    # ─── Schedule ────────────────────────────────────────────────────
    date_planned = fields.Date('Planned Date', required=True,
                                default=fields.Date.context_today)
    date_done = fields.Date('Completed Date')

    # ─── State ───────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True,
        group_expand='_expand_states')

    # ─── Findings ────────────────────────────────────────────────────
    checklist_line_ids = fields.One2many(
        'facility.inspection.line', 'inspection_id',
        string='Checklist Items')
    overall_rating = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('critical', 'Critical'),
    ], string='Overall Rating', tracking=True)
    finding_notes = fields.Html('Findings & Observations')
    recommendation = fields.Text('Recommendations')

    # ─── Computed ────────────────────────────────────────────────────
    pass_count = fields.Integer('Passed', compute='_compute_checklist_stats')
    fail_count = fields.Integer('Failed', compute='_compute_checklist_stats')
    total_items = fields.Integer('Total Items', compute='_compute_checklist_stats')
    pass_rate = fields.Float('Pass Rate (%)', compute='_compute_checklist_stats')

    @api.model
    def _expand_states(self, states, domain):
        return [key for key, _val in self._fields['state'].selection]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'facility.inspection') or 'New'
        return super().create(vals_list)

    @api.depends('checklist_line_ids.result')
    def _compute_checklist_stats(self):
        for rec in self:
            lines = rec.checklist_line_ids
            rec.total_items = len(lines)
            rec.pass_count = len(lines.filtered(lambda l: l.result == 'pass'))
            rec.fail_count = len(lines.filtered(lambda l: l.result == 'fail'))
            rec.pass_rate = (
                (rec.pass_count / rec.total_items * 100)
                if rec.total_items else 0.0)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.building_id and self.building_id.project_id != self.project_id:
            self.building_id = False

    @api.onchange('building_id')
    def _onchange_building_id(self):
        if self.building_id:
            if self.building_id.project_id:
                self.project_id = self.building_id.project_id
        if self.unit_id and self.unit_id.building_id != self.building_id:
            self.unit_id = False

    # ─── Actions ─────────────────────────────────────────────────────
    def action_schedule(self):
        self.write({'state': 'scheduled'})

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_complete(self):
        self.write({
            'state': 'done',
            'date_done': fields.Date.context_today(self),
        })

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft', 'date_done': False})

    def action_apply_template(self):
        """Open wizard-like action to select a checklist template."""
        self.ensure_one()
        return {
            'name': _('Apply Checklist Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'facility.checklist.template',
            'view_mode': 'list',
            'target': 'new',
            'context': {'default_inspection_id': self.id},
        }


class FacilityInspectionLine(models.Model):
    _name = 'facility.inspection.line'
    _description = 'Facility Inspection Checklist Item'
    _order = 'sequence, id'

    inspection_id = fields.Many2one(
        'facility.inspection', string='Inspection',
        required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Check Item', required=True)
    category_id = fields.Many2one(
        'facility.service.category', string='Category')
    result = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('na', 'N/A'),
    ], string='Result')
    notes = fields.Char('Notes')
    photo = fields.Image('Photo', max_width=1024, max_height=1024)
