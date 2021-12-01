#############################################################################
#
#    PT. PROWEB INDONESIA.
#
#    Copyright (C) 2021-TODAY PROWEB INDONESIA(<https://www.proweb.co.id>)
#    Author: Junus J Djunawidjaja
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import api, fields, models


class KartuStokReport(models.AbstractModel):
    _name = 'report.proweb_kartu_stok.print_kartu_stok_proweb'
    _description = 'Print Kartu Stok Report ProWeb'

    @api.model
    def _get_report_values(self, docids, data=None):
        if data:
            if data['ids'] and data['context']['active_model'] in ['product.template', 'product.product']:
                docs = self.env['product.product'].browse(data['ids'])
                location = self.env['stock.location'].browse(data['location_id'])
                location_name = location['display_name'].split('/')[0]
                return {
                    'ids': docs.ids,
                    'model': 'product.product',
                    'location_id': data['location_id'],
                    'location_name': location_name,
                    'docs': docs,
                }


class KartuStokWizard(models.TransientModel):
    _name = 'kartu.stok.wizard'
    _description = "Kartu Stok Wizard"
    
    location_id = fields.Many2one('stock.location', string="Location", default=8, required=True)
    
    def action_kartu_stok_wizard(self):
        active_ids_tmp = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        if active_model == 'product.template':
            active_ids = self.env['product.product'].search(
                [('product_tmpl_id', 'in', active_ids_tmp),
                ('active', '=', True)]).ids
        else:
            active_ids = active_ids_tmp  # product.product                               
        products = self.env['product.product'].browse(active_ids)
        if self.read()[0]['location_id']:
            data = { 
                'location_id': self.read()[0]['location_id'][0],
                'ids': active_ids,
            }
        return self.env.ref('proweb_kartu_stok.action_print_kartu_stok_proweb').report_action(products, data=data)
