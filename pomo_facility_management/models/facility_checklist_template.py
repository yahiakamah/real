# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FacilityChecklistTemplate(models.Model):
    _name = 'facility.checklist.template'
    _description = 'Facility Inspection Checklist Template'
    _order = 'name'

    name = fields.Char('Template Name', required=True)
    category_id = fields.Many2one(
        'facility.service.category', string='Service Category')
    inspection_type = fields.Selection([
        ('routine', 'Routine Inspection'),
        ('pre_handover', 'Pre-Handover'),
        ('post_handover', 'Post-Handover'),
        ('annual', 'Annual Inspection'),
        ('safety', 'Safety Inspection'),
    ], string='Inspection Type')
    active = fields.Boolean('Active', default=True)
    line_ids = fields.One2many(
        'facility.checklist.template.line', 'template_id',
        string='Checklist Items')
    item_count = fields.Integer('Items', compute='_compute_item_count')

    @api.depends('line_ids')
    def _compute_item_count(self):
        for tmpl in self:
            tmpl.item_count = len(tmpl.line_ids)

    def action_apply_to_inspection(self, inspection):
        """Copy template lines to an inspection."""
        InspectionLine = self.env['facility.inspection.line']
        for tmpl in self:
            for line in tmpl.line_ids:
                InspectionLine.create({
                    'inspection_id': inspection.id,
                    'sequence': line.sequence,
                    'name': line.name,
                    'category_id': line.category_id.id,
                })


class FacilityChecklistTemplateLine(models.Model):
    _name = 'facility.checklist.template.line'
    _description = 'Facility Checklist Template Item'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'facility.checklist.template', string='Template',
        required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Check Item', required=True)
    category_id = fields.Many2one(
        'facility.service.category', string='Category')
