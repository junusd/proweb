#############################################################################
#
#    PT. PROWEB INDONESIA.
#
#    Copyright (C) 2022-TODAY PROWEB INDONESIA(<https://www.proweb.co.id>)
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

{
	"name": "Proweb Bank BCA Online Account Statements Import",
	"version": "1.0",
	"category": "Account",
	"author": "PT. Proweb Indonesia",
	"company": "PT. Proweb Indonesia",
	"maintainer": "PT. Proweb Indonesia",
	"website": "https://www.proweb.co.id",
	"summary": """Proweb Bank BCA Online Account Statements Import.""",
	"description": """
Proweb Bank BCA Online Account Statements Import
""",
	"depends": [
        "account",
    ],
	"data": [
        'security/proweb_bank_bca_security.xml',
        'security/ir.model.access.csv',
        "views/online_bank_statement_provider.xml",
        "views/proweb_bank_bca.xml",
        "wizard/proweb_bank_bca_wizard.xml",
        "views/account_journal.xml",
        ],
	'images': ['static/description/images/main_report.gif'],
	"application": True,
	"installable": True,
	"auto_install": False,
	"license": "AGPL-3",
}
