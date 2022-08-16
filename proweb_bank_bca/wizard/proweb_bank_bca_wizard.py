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

from odoo import fields, models

class ProwebBankBCAImportWizard(models.TransientModel):
    _name = 'proweb.bank.bca.wizard'
    _description = "Proweb Bank BCA Wizard"
    
    file_csv = fields.Binary(string="File CSV", help="Please Input .CSV File", required=True)

    def action_file_csv(self):
        """Pull statements from providers and then show list of statements."""
        active_ids_tmp = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_account_journal = self.env[active_model].browse(active_ids_tmp)
        active_account_journal.online_bank_statement_provider_id._pull(self.file_csv)
        
        action = active_account_journal.env.ref("account.action_bank_statement_tree").sudo().read([])[0]
        action["context"] = {
            "search_default_journal_id": active_account_journal.id
        }
        return action
