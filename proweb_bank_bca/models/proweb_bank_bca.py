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

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.base.models.res_bank import sanitize_account_number
from odoo.addons.base.models.res_partner import _tz_get

import re
import datetime
import pytz
import csv
import base64

from .klikbca import KlikBCAParser
from passlib.hash import cisco_type7
import logging
_logger = logging.getLogger(__name__)

retrieve_days = 31
klikbca_pending_date = '1901-01-01'

selBankBCA = 'bca'
selBankOther = 'other'

selMutationCR = 'cr'
selMutationDB = 'db'
selMutationOther = 'ot'

selFViewOperator = 'op'
selFViewOther = 'ot'

def str_to_float(str):
    return float(str.replace(",", ""))

class proweb_bank_bca(models.Model):
    """ Proweb Bank BCA """
    _name = "proweb_bank_bca"
    _description = "Proweb Bank BCA"
    _order = 'id desc'

    date = fields.Date(string='Date', required=True)
    bank = fields.Selection([(selBankBCA, 'BCA'), (selBankOther, 'Other')], string='Bank', required=True)
    ttype = fields.Char(string='Type', size=22)
    description = fields.Char(string='Description', size=200)
    description_raw = fields.Char(string='Description Raw', size=200)
    ent = fields.Char(string='Entity', size=50)
    bankcode = fields.Char(string='BankCode', size=10)
    amount = fields.Float(string='Amount', default=0)
    mutation = fields.Selection([(selMutationCR, 'CR'), (selMutationDB, 'DB'),
                                 (selMutationOther, 'Other')], string='Mutation')
    checked = fields.Boolean(string='Checked', default=False)
    fview = fields.Selection([(selFViewOperator, 'Operator'), (selFViewOther, 'Other')],
                             string='Filtered View')
    note = fields.Char(String="Note", size=100)
    dup_no = fields.Integer(string="Duplicate #", default=0)
    balance = fields.Float(string='Balance', default=0)

    def name_get(self):
        bank_list = {'other': 'Other', 'bca': 'BCA'}
        result = []
        for record in self:
            result.append(
                (record.id,
                u"[%s] %s %s" % (record.id, bank_list[record.bank], record.date)
                ))
        return result

    def insert_first_balance(self, balance, fromdate):
        if len(self.search([])) == 0:
            balance_float = str_to_float(balance)
            self.sudo().create({
                'date': fromdate,
                'bank': selBankBCA,
                'ttype': 'SALDO AWAL',
                'amount': balance_float,
                'mutation': selMutationCR,
                'fview': selFViewOther,
                'balance':balance_float})

    def get_csv(self, file_csv):
        enterprise = False
        transactions = []
        balances = []
        
        file = base64.b64decode(file_csv)
        file_string = file.decode('utf-8')
        file_string = file_string.split('\n')

        if file_string:            
            csv_reader = csv.reader(file_string, delimiter=',')
            line_count = 0
            for row in csv_reader:
                if line_count == 0 and row and 'Informasi Rekening - Mutasi Rekening' in row[0]:
                    enterprise = True
                if enterprise:
                    #KlikBCA CSV Enterprise
                    if line_count >= 7:
                        if len(row) and 'Saldo Awal' in row[0]:
                            lst = row[0].split()
                            balances.append(lst[-1])
                        elif len(row) and 'Kredit' in row[0]:
                            lst = row[0].split()
                            balances.append(balances[1]) # on Enterpise Debet first then Kredit so need to be swap.
                            balances[1] = lst[-1]
                        elif len(row) and 'Debet' in row[0]:
                            lst = row[0].split()
                            balances.append(lst[-1]) #need to swap with Kredit
                        elif len(row) and 'Saldo Akhir' in row[0]:
                            lst = row[0].split()
                            balances.append(lst[-1])
                        elif len(row):
                            row.append(row[4])
                            lst = row[3].split()
                            row[4]=lst[1]
                            row[3]=lst[0]
                            transactions.append(row)                
                else:
                    #KlikBCA CSV Individual
                    if line_count >= 5:
                        if len(row) and 'Saldo Awal' in row[0]:
                            balances.append(row[2])
                        elif len(row) and 'Kredit' in row[0]:
                            balances.append(row[2])
                        elif len(row) and 'Debet' in row[0]:
                            balances.append(row[2])
                        elif len(row) and 'Saldo Akhir' in row[0]:
                            balances.append(row[2])
                        elif len(row):
                            row[0] = row[0].replace("'","")
                            row[2] = row[2].replace("'","")
                            transactions.append(row)
                line_count += 1        
        return transactions, balances
    
    @api.model
    def transaction_update_bca(self, online_bank_statement_provider = None, file_csv = None):
        bca_online_status = False
        transactions = None
        balances = None
        today = datetime.date.today()
        fromdate_tmp = datetime.date.today() - datetime.timedelta(days=retrieve_days)

        if file_csv:
            transactions, balances = self.get_csv(file_csv)
        else:
            if online_bank_statement_provider:
                bank_config = online_bank_statement_provider
            else:
                bank_config = self.env['online.bank.statement.provider'].search([('bank','=','bca')], order='id asc', limit=1)
            
            ### Decode password ###       
            if bank_config.password and bank_config.password[0] == '#':
                bank_config_passw = cisco_type7.decode(bank_config.password[1:])
            else:
                bank_config_passw = bank_config.password
            #######################
            
            bca = KlikBCAParser(bank_config.username, bank_config_passw)
            balance = []
            bca.login()
            if bca.login_status:            
                data_tmp = bca.daily_statements(fromdate_tmp.strftime('%d/%m/%Y'), today.strftime('%d/%m/%Y'))
                bca.logout()
                bca_online_status = True
                transactions = data_tmp[1][1]
                balances = data_tmp[2][1]
        
        if file_csv or bca_online_status:                        
            
            self.insert_first_balance(balances[0], fromdate_tmp)

            fromdate = fromdate_tmp.strftime('%Y-%m-%d')
            #Add dup_no Column
            transactionsLen = len(transactions)
            for arrayNo in range(transactionsLen):
                dup_no = 0
                transaction = transactions[arrayNo]
                if len(transaction)==6:
                    transactions[arrayNo] += (dup_no,)
                    searchNo = arrayNo + 1
                    while searchNo < transactionsLen:
                        if len(transactions[searchNo])==6 and transaction[0] == transactions[searchNo][0] and transaction[1] == transactions[searchNo][1] and transaction[2] == transactions[searchNo][2] and transaction[3] == transactions[searchNo][3] and transaction[4] == transactions[searchNo][4] and transaction[5] == transactions[searchNo][5]:
                            dup_no += 1
                            transactions[searchNo] += (dup_no,)
                        searchNo += 1

            self._cr.execute("SELECT id, write_date, date, ttype, description, ent, bankcode, amount, mutation, dup_no, balance FROM " + self._name + " WHERE bank = '%s' AND write_date >= '%s'" % (selBankBCA, fromdate))
            recs = self._cr.fetchall()

            today_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            todayYear = int(today.strftime('%Y'))

            for tran in transactions:
                # if 'KR OTOMATIS' in tran[1]:
                print(tran)
                match_date = tran[0].rstrip().split('/')
                if match_date[0] == 'PEND':
                    date = datetime.date(1901, 1, 1)
                else:
                    date = datetime.date(todayYear, int(match_date[1]), int(match_date[0]))
                    delta = today - date
                    if delta.days <= -retrieve_days:
                        date = datetime.date(todayYear-1, int(match_date[1]), int(match_date[0]))
                bank = selBankBCA
                description = ''
                description_raw = tran[1]
                ent = ''
                mutation = ''
                dup_no = tran[6]

                bankcode = tran[2]
                amount = str_to_float(tran[3])
                balance = str_to_float(tran[5])

                if tran[4] == 'CR':
                    mutation = selMutationCR
                elif tran[4] == 'DB':
                    mutation = selMutationDB
                else:
                    mutation = selMutationOther

                match_tran = [x.strip() for x in tran[1].split('\n')]
                ttype = match_tran[0]

                #Try to parsing 'ent' -> person name do transaction
                match_tran_len = len(match_tran)
                if ttype in ['TRSF E-BANKING CR', 'TRSF E-BANKING DB']:
                    description = match_tran[1]
                    noTran = 2
                    match_tran_len_1 = match_tran_len-1
                    while noTran < match_tran_len_1:
                        description += "\n" + match_tran[noTran]
                        noTran += 1
                    ent = match_tran[match_tran_len_1]
                elif ttype in ['SWITCHING CR', 'BI-FAST CR']:
                    pattern_tran = re.compile(r"TRANSFER   DR \d+ (([a-zA-Z\d\-]+ )*[a-zA-Z\d\-]+)(  +)*")
                    match_tran2 = pattern_tran.findall(match_tran[1])
                    if match_tran2:
                        ent = match_tran2[0][0]
                    description = match_tran[1]
                elif ttype in ['KR OTOMATIS']:
                    pattern_tran = re.compile(r"  +(([a-zA-Z\d\-]+ )*[a-zA-Z\d\-]+)ID101W4-")
                    if len(match_tran) > 1 :
                        match_tran2 = pattern_tran.findall(match_tran[1])
                        if match_tran2:
                            ent = match_tran2[0][0]                        
                        description = match_tran[1]
                    else:
                        description = match_tran[0]
                elif match_tran[0] == 'SETORAN TUNAI':
                    if match_tran_len>1:
                        description = match_tran[1]
                        noTran = 2
                        match_tran_len_1 = match_tran_len-1
                        while noTran < match_tran_len_1:
                            description += "\n" + match_tran[noTran]
                            noTran += 1
                elif ttype in ['TARIKAN TUNAI', 'BUNGA', 'PAJAK BUNGA', 'BIAYA ADM', 'CR KOREKSI BUNGA', 'DR KOREKSI BUNGA']:
                    pass
                else:
                    description = tran[1]

                #Find duplicate previous transaction
                found = False
                for rec in recs:
                    if (ttype == rec[3] and description == rec[4] and ent == rec[5] and
                            amount == rec[7] and mutation == rec[8] and dup_no == rec[9]):
                        if (rec[2].strftime('%Y-%m-%d') in klikbca_pending_date) and str(date) not in klikbca_pending_date:
                            self._cr.execute("UPDATE bank_bca SET date='%s', write_date='%s' WHERE id=%s"
                                             % (date, today_now, rec[0]))
                            found = True
                            break
                        else: 
                            if date == rec[2]:
                                found = True
                                break
                
                #Hide transaction from specific 'ent' company/person
                if not found:
                    #print "BCA: ", date," ", bank," ",ttype," ", description," ", ent,
                    #   " ", bankcode," ", amount," ",mutation
                    fview = selFViewOther
                    # if ((amount <= 6000000) and (mutation == selMutationCR) and
                    #         (ttype != 'Bunga Rekening') and (ttype != 'BUNGA') and ('KOREKSI BUNGA' not in ttype):
                    #     fview = selFViewOperator
                    self.sudo().create({
                        'date':date,
                        'bank':bank,
                        'ttype':ttype,
                        'description':description,
                        'description_raw':description_raw,
                        'ent':ent,
                        'bankcode':bankcode,
                        'amount':amount,
                        'mutation':mutation,
                        'fview':fview,
                        'dup_no':dup_no,
                        'balance':balance})

            #########################################################
            # Check if saldo balance
            #########################################################
            # check total credit, debit, beginning saldo from bank_bca sql table.
            self._cr.execute("""
            SELECT SUM(sa) sa1, SUM(cr) cr1, SUM(db) db1, SUM(amount_dbcr) dbcr1 FROM (
                SELECT id, date,
                CASE
                    WHEN ttype = 'SALDO AWAL' THEN amount
                    else 0
                END AS sa,
                CASE
                    WHEN mutation = 'db' THEN - amount
                    else 0
                END AS db,
                CASE
                    WHEN mutation = 'cr' and ttype <> 'SALDO AWAL' THEN amount
                    else 0
                END AS cr,
                CASE
                    WHEN mutation = 'db' THEN - amount
                    ELSE amount
                END AS amount_dbcr
                FROM """ + self._name +""") bg_amount group by (date <> '%s' and date < '%s') order by sa1""" % (klikbca_pending_date, fromdate))
            recs = self._cr.fetchall()
            num_format = "{:,.2f}".format
            if len(recs) > 1 :
                rec_beginning_balance = recs[1][3]
                rec_cr = num_format(round(recs[0][1],2))
                rec_db = num_format(round(-recs[0][2],2))
            elif len(recs) == 1 :
                rec_beginning_balance = recs[0][0]
                rec_cr = num_format(round(recs[0][1],2))
                rec_db = num_format(round(-recs[0][2],2))
            else:
                rec_beginning_balance = 0
                rec_cr = 0
                rec_db = 0
            if not (balances[0] == num_format(round(rec_beginning_balance,2)) and balances[1] == rec_cr and balances[2] == rec_db):
                warningStr = (
                    'WARNING: Balance difference between odoo and real bank statement!\n'
                    '                Website            Odoo\n'
                    'SALDO AWAL    : %s  %s\n'
                    'MUTASI KREDIT : %s  %s\n'
                    'MUTASI DEBIT  : %s  %s\n'
                    'SALDO AKHIR   : %s  %s\n'              
                    % (
                        balances[0], num_format(round(rec_beginning_balance,2)),
                        balances[1], rec_cr,
                        balances[2], rec_db,
                        balances[3], num_format(round(rec_beginning_balance + recs[0][3]))
                    ))                
                _logger.warning(
                    warningStr,
                    exc_info=True,
                )
                raise Exception(warningStr)
        return True


#########################################################

class AccountJournal(models.Model):
    _inherit = "account.journal"

    online_bank_statement_provider = fields.Selection(
        selection=lambda self: self.env[
            "account.journal"
        ]._selection_online_bank_statement_provider(),
        help="Select the type of service provider (a model)",
    )
    online_bank_statement_provider_id = fields.Many2one(
        string="Statement Provider",
        comodel_name="online.bank.statement.provider",
        ondelete="restrict",
        copy=False,
        help="Select the actual instance of a configured provider (a record).\n"
        "Selecting a type of provider will automatically create a provider"
        " record linked to this journal.",
    )

    def __get_bank_statements_available_sources(self):
        result = super().__get_bank_statements_available_sources()
        result.append(("online", _("Online")))
        return result

    @api.model
    def _selection_online_bank_statement_provider(self):
        return self.env["online.bank.statement.provider"]._get_available_services()

    @api.model
    def values_online_bank_statement_provider(self):
        """Return values for provider type selection in the form view."""
        res = self.env["online.bank.statement.provider"]._get_available_services()
        if self.user_has_groups("base.group_no_one"):
            res += [("dummy", "Dummy")]
        return res

    def _update_online_bank_statement_provider_id(self):
        """Keep provider synchronized with journal."""
        OnlineBankStatementProvider = self.env["online.bank.statement.provider"]
        for journal in self.filtered("id"):
            provider_id = journal.online_bank_statement_provider_id
            if journal.bank_statements_source != "online":
                journal.online_bank_statement_provider_id = False
                if provider_id:
                    provider_id.unlink()
                continue
            if provider_id.service == journal.online_bank_statement_provider:
                continue
            journal.online_bank_statement_provider_id = False
            if provider_id:
                provider_id.unlink()
            # fmt: off
            journal.online_bank_statement_provider_id = \
                OnlineBankStatementProvider.create({
                    "journal_id": journal.id,
                    "service": journal.online_bank_statement_provider,
                })
            # fmt: on

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        if "bank_statements_source" in vals or "online_bank_statement_provider" in vals:
            rec._update_online_bank_statement_provider_id()
        return rec

    def write(self, vals):
        res = super().write(vals)
        if "bank_statements_source" in vals or "online_bank_statement_provider" in vals:
            self._update_online_bank_statement_provider_id()
        return res


class OnlineBankStatementProviderBCA(models.Model):
    _name = "online.bank.statement.provider"
    _description = "Online Bank Statement Provider"


    company_id = fields.Many2one(related="journal_id.company_id", store=True)
    active = fields.Boolean(default=True)
    name = fields.Char(string="Name", compute="_compute_name", store=True)
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        required=True,
        readonly=True,
        ondelete="cascade",
        domain=[("type", "=", "bank")],
    )
    currency_id = fields.Many2one(related="journal_id.currency_id")
    account_number = fields.Char(
        related="journal_id.bank_account_id.sanitized_acc_number"
    )
    tz = fields.Selection(
        selection=_tz_get,
        string="Timezone",
        default=lambda self: self.env.context.get("tz"),
        help=(
            "Timezone to convert transaction timestamps to prior being"
            " saved into a statement."
        ),
    )
    service = fields.Selection(
        selection=lambda self: self._selection_service(),
        required=True,
        readonly=True,
    )

    bank = fields.Char(string="Bank", default = 'bca')
    username = fields.Char(string='UserName', default='')
    password = fields.Char(string='Password')
    last_id = fields.Integer(string="Last ID", default = 0)

    allow_empty_statements = fields.Boolean(string="Allow empty statements")

    _sql_constraints = [
        (
            "journal_id_uniq",
            "UNIQUE(journal_id)",
            "Only one online banking statement provider per journal!",
        ),
    ]


    def write(self, vals):
        if vals.get('password'):
        ### Encode password ###       
            if vals['password'][0] != '#': 
                vals['password'] = '#' + cisco_type7.hash(vals['password'])            
        #######################
        res = super().write(vals)
        return res

    @api.model
    def _selection_service(self):
        return self._get_available_services()

    @api.model
    def values_service(self):
        return self._get_available_services()

    @api.depends("service", "journal_id.name")
    def _compute_name(self):
        """We can have multiple providers/journals for the same service."""
        for provider in self:
            provider.name = " ".join([provider.journal_id.name, provider.service])





    @api.model
    def _get_available_services(self):
        return [
            ("klikbca", "klikbca.com"),
        ]

    def _obtain_statement_data(self):
        self.ensure_one()
        if self.service != "klikbca":
            return super()._obtain_statement_data()
        return self._bca_obtain_statement_data()


    def _bca_obtain_statement_data(self, file_csv = None):
        """Translate information from bca to Odoo bank statement lines."""
        self.ensure_one()
        
        self.env['proweb_bank_bca'].transaction_update_bca(self, file_csv)
        if self.last_id and self.last_id > 0:
            transaction_lines = self.env['proweb_bank_bca'].search([('id','>', self.last_id),('date', '!=', klikbca_pending_date)])        
        else:
            transaction_lines = self.env['proweb_bank_bca'].search([('date', '!=', klikbca_pending_date)])        
        
        new_transactions = []
        sequence = 0
        last_id = 0
        for transaction in transaction_lines:
            sequence += 1
            vals_line = {
                "sequence": sequence,
                "date": transaction.date,  #date
                "payment_ref": transaction.description_raw if transaction.description_raw else transaction.ttype, #description
                "amount": -transaction.amount if transaction.mutation == selMutationDB else transaction.amount, # amount (- if db )
            }
            new_transactions.append(vals_line)
            if last_id < transaction.id :
                last_id = transaction.id
        if new_transactions:
            self.update({"last_id": last_id})
            return new_transactions, {}
        return

    def _create_or_update_statement(self, data):
        """Create or update bank statement with the data retrieved from provider."""
        self.ensure_one()
        AccountBankStatement = self.env["account.bank.statement"]
        if not data:
            data = ([], {})
        if not data[0] and not data[1] and not self.allow_empty_statements:
            return
        lines_data, statement_values = data
        if not lines_data:
            lines_data = []
        if not statement_values:
            statement_values = {}
        statement_date = datetime.date.today()
        statement = AccountBankStatement.search(
            [
                ("journal_id", "=", self.journal_id.id),
                ("state", "=", "open"),
                ("date", "=", statement_date),
            ],
            limit=1,
        )
        if not statement:
            statement_values.update(
                {
                    "name": "%s/%s"
                    % (self.journal_id.code, statement_date.strftime("%Y-%m-%d")),
                    "journal_id": self.journal_id.id,
                    "date": statement_date,
                }
            )
            statement = AccountBankStatement.with_context(
                journal_id=self.journal_id.id,
            ).create(
                # NOTE: This is needed since create() alters values
                statement_values.copy()
            )
        filtered_lines = self._get_statement_filtered_lines(
            lines_data)
        statement_values.update(
            {"line_ids": [[0, False, line] for line in filtered_lines]}
        )
        if "balance_start" in statement_values:
            statement_values["balance_start"] = float(statement_values["balance_start"])
        if "balance_end_real" in statement_values:
            statement_values["balance_end_real"] = float(
                statement_values["balance_end_real"]
            )
        statement.write(statement_values)


    def _sanitize_bank_account_number(self, bank_account_number):
        """Hook for extension"""
        self.ensure_one()
        return sanitize_account_number(bank_account_number)
    
    
    
    def _pull(self, file_csv = None):
        for provider in self:
            data = provider._bca_obtain_statement_data(file_csv)
            provider._create_or_update_statement(data)


    def _get_statement_filtered_lines(self, lines_data):
        """Get lines from line data, but only for the right date."""
        AccountBankStatementLine = self.env["account.bank.statement.line"]
        provider_tz = pytz.timezone(self.tz) if self.tz else pytz.utc
        filtered_lines = []
        for line_values in lines_data:
            date = line_values["date"]
            if not isinstance(date, datetime.datetime):
                date = fields.Datetime.from_string(date)
            if date.tzinfo is None:
                date = date.replace(tzinfo=pytz.utc)
            date = date.astimezone(pytz.utc).replace(tzinfo=None)
            date = date.replace(tzinfo=pytz.utc)
            line_values["date"] = date
            bank_account_number = line_values.get("account_number")
            if bank_account_number:
                sanitized_account_number = self._sanitize_bank_account_number(
                    bank_account_number
                )
                line_values["account_number"] = sanitized_account_number
                self._update_partner_from_account_number(line_values)
            if not line_values.get("payment_ref"):
                line_values["payment_ref"] = line_values.get("ref")
            filtered_lines.append(line_values)
        return filtered_lines


    def action_pull(self):
        """Pull statements from providers and then show list of statements."""
        active_ids_tmp = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_account_journal = self.env[active_model].browse(active_ids_tmp)
        active_account_journal.online_bank_statement_provider_id._pull()
        
        action = active_account_journal.env.ref("account.action_bank_statement_tree").sudo().read([])[0]
        action["context"] = {
            "search_default_journal_id": active_account_journal.id
        }
        return action
