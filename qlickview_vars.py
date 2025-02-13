import sublime
import sublime_plugin
import os
import re
import xml.etree.ElementTree as etree
import csv
import sys
import datetime
from sublime import Region
from .util.qvvars import QlikViewCommandExpander
import json
#from .util.qvvars import QvVarFileReader


EXT_QLIKVIEW_VARS  = ".qlikview-vars"
class QlikviewVariableFileListener(sublime_plugin.EventListener):
    """Save variables in one of export formats 
    along with current expression file in YAML like format (extentsion EXT_QLIKVIEW_VARS)

    Implements:
        on_post_save"""
    EXT_QLIKVIEW_VARS  = ".qlikview-vars"
    EXT_QLIKVIEW_QDF_CSV = ".csv"
    EXT_QLIKVIEW_TABLE_CSV = ".table.csv"
    EXT_QLIKVIEW_VARS_QVS = ".vars.qvs"
    EXT_QLIKVIEW_VARS_JSON = ".json"
    modulesettings = None
    reader = None
    def is_ST3(self):
        ''' check if ST3 based on python version '''
        version = sys.version_info
        if isinstance(version, tuple):
            version = version[0]
        elif getattr(version, 'major', None):
            version = version.major
        return (version >= 3)
    def on_post_save(self, view):
        fn = view.file_name()
        if (fn.endswith(self.EXT_QLIKVIEW_VARS)):
            view.window().run_command("qlikview_variables_export")

class QlikviewVariablesExportCommand(sublime_plugin.WindowCommand):
    """Save variables in one of export formats 
    along with current expression file in YAML like format (extentsion EXT_QLIKVIEW_VARS)

    Implements:
        on_post_save"""
    EXT_QLIKVIEW_VARS  = ".qlikview-vars"
    EXT_QLIKVIEW_QDF_CSV = ".csv"
    EXT_QLIKVIEW_TABLE_CSV = ".table.csv"
    EXT_QLIKVIEW_VARS_QVS = ".vars.qvs"
    EXT_QLIKVIEW_VARS_JSON = ".json"
    modulesettings = None
    reader = None
    def is_ST3(self):
        ''' check if ST3 based on python version '''
        version = sys.version_info
        if isinstance(version, tuple):
            version = version[0]
        elif getattr(version, 'major', None):
            version = version.major
        return (version >= 3)
    def run(self, commandVariant=None):
        view = self.window.active_view()
        fn = view.file_name()
        if (fn.endswith(self.EXT_QLIKVIEW_VARS)):
            self.modulesettings = view.settings()
            self.reader = QvVarFileReader(self.modulesettings)
            self.regenerate_expression_tab_file(view.file_name())

    def regenerate_tab_file_content(self,path, onload=False):
        (name, ext) = os.path.splitext(os.path.basename(path))
        f = None
        if self.is_ST3():
            f = open(path, 'r', encoding="utf-8")
        else:
            f = open(path, 'rb')
        read = f.read()
        f.close()

        try:
            self.reader.parse_content(read)
        except Exception as e:
            msg  = isinstance(e, SyntaxError) and str(e) or "Error parsing QlikView expression "
            msg += " in file `%s` line: %d" % (path, self.reader.linenum)
            if onload:
                # Sublime Text likes "hanging" itself when an error_message is pushed at initialization
                print("Error: " + msg)
            else:
                sublime.error_message(msg)
            if not isinstance(e, SyntaxError):
                print(e)  # print the error only if it's not raised intentionally
                return None
    def regenerate_expression_tab_file(self,path, onload=False, force=False):
        start = datetime.datetime.utcnow()
        output_mode = self.modulesettings.get("output_mode","QDF")
        expandVariables = self.modulesettings.get("expand_variables",False);
        print("expandVariables: %s" % expandVariables)
        if output_mode == 'QDF':
            outExt = self.EXT_QLIKVIEW_QDF_CSV
        elif output_mode == 'QVS':
            outExt = self.EXT_QLIKVIEW_VARS_QVS
        elif output_mode == 'JSON':
            outExt = self.EXT_QLIKVIEW_VARS_JSON            
        elif output_mode == 'CSV':
            outExt = self.EXT_QLIKVIEW_TABLE_CSV
        else:
            sublime.error_message('Unknown output_format %s. Known formats are QDF (Csv file QlikView Deployment framework), QVS (Plain include script), CSV (Plain tabular csv)')
        outPath = path.replace(self.EXT_QLIKVIEW_VARS,outExt)
        self.regenerate_tab_file_content(path, onload=onload)
        f = None
        if self.is_ST3():
            if output_mode == 'QDF':
                enc = 'utf-8'
            elif output_mode == 'CSV':
                enc = 'utf-8-sig'
            else: 
                enc = 'utf-8-sig'
            f = open(outPath, 'w', encoding=enc, newline='')
        else:
            f = open(outPath,'wb')
        if expandVariables == True: 
            print('Expandind variables')
            expander = QlikViewVariableExpander(self.reader.output)
            expander.expandAll()
            for exp in self.reader.expressions:
                exp['expandedDefinition'] = expander.exp_dict[exp.get('name')]
        if output_mode == 'QDF':
            writer = csv.writer(f)
            writer.writerow(['VariableName','VariableValue','Comments','Priority'])
            for row in self.reader.output:
                writer.writerow(['%s %s' % (row[0] , row[1]), expander.exp_dict[row[1]] if expandVariables else row[2], row[3], row[4]])
        elif output_mode == 'QVS':
            f.write('//////THIS IS AUTOGENERATED FILE. DO NOT EDIT IT DIRECTLY!!!!!!!!!!!!!\n\n')
            for row in self.reader.output:
                exp = expander.exp_dict[row[1]] if expandVariables else row[2]
                if '$(' in exp:
                    command = 'let'
                    exp = exp.replace("'","~~~")
                    exp = exp.replace("$(","@(")
                    exp = "replace(replace('%s','~~~', chr(39)), '@(', chr(36) & '(')" % exp
                else:
                    command = row[0]
                varName = row[1]
                line = "%s %s = %s;\n" % (command,varName,exp) 
                f.write(line)
        elif output_mode == 'JSON':
            jsonContent = json.dumps(self.reader.expressions, sort_keys=True, indent=4, ensure_ascii=False)
            f.write(jsonContent)    
        elif output_mode == 'CSV':
            writer = csv.writer(f)
            writer.writerow(['ExpressionName','Label','Comment','Description','Section','Definition','Width'])
            for exp in self.reader.expressions:
                writer.writerow([exp.get('name'),exp.get('label'),exp.get('comment'),exp.get('description'),None,exp.get('expandedDefinition') if expandVariables else exp.get('definition'),exp.get('width')])        
        f.close()
        print(' Saving elapsed: ' + str(datetime.datetime.utcnow()-start))


class QvVarFileReader:
    ALLOWED_TAGS = ('label','comment', 'definition','backgroundColor','fontColor','textFormat',
        'tag','separator','#define', 'macro','description','enableCondition',
        'showCondition','sortBy','visualCueUpper','visualCueLower','width','symbol',
        'thousandSymbol','millionSymbol','billionSymbol','family','type', 'selectorLabel', 'format', 'calendar')
    FIELDS_TO_SKIP = ('definition','tag','set','let','command','name','separator','macro','description', 'family', 'type', 'selectorLabel', 'format')
    NAME_MAP = {}

    line_template = re.compile(r'^(?P<key>\w+?):\s*(?P<val>.*)$')
    define_template = re.compile(r'^#define\s*(?P<key>\S+)\s+(?P<val>.*)$')
    param_template = re.compile(r'^\s*\-\s*(?P<val>.*)$')

    linenum = 0
    defs = {}
    macro = []
    output = []
    expressions = []
    define_directives = {}
    modulesettings = None
    def __init__(self,modulesettings):
        self.linenum = 0
        self.defs = {}
        self.macro = []
        self.output = []
        self.define_directives = {}
        self.modulesettings = modulesettings
        self.currentSection = ''
    def put_row(self, key, value, command, comment, priority):
            self.output.append([command.upper(), key ,value, comment, priority])
    def parse_content(self,text):
        self.NAME_MAP = {}
        mappings = self.modulesettings.get('mappings',{})
        for tag in self.ALLOWED_TAGS:
            self.NAME_MAP[tag] = mappings.get(tag,tag);
        self.NAME_MAP['separator'] = self.modulesettings.get('separator','.')
        expression = {}
        defs = {}
        define_directives = {}
        self.linenum = 0
        self.macro = []
        self.output = []
        self.expressions = []
        def expand_macro():
            if defs.get(self.macro[0]) is None:
                raise SyntaxError('Parsing error: definition for macro `%s` is not found' % self.macro[0])
            result = defs[self.macro[0]]
            i = 1
            while i < len(self.macro):
                param = self.macro[i]
                subs = '$%s' % str(i)
                if not subs in result:
                    print('macro',self.macro)
                    raise SyntaxError('Parsing error: definition for macro `%s` does not contain substring %s' % (self.macro[0],subs))    
                result = result.replace(subs,param)
                i = i + 1
            return result
        def init_expression():
            self.macro = []
            expression = {}
        def process_expression(exp):
            if exp == {}:
                return None
            if exp.get('name') is None:
                return'Parsing error: `name` property is absent'
            if exp['name'] in defs:
                return 'Parsing error: duplicate expression with name `%s`' % exp['name']
            if exp.get('definition') is not None and exp.get('macro') is not None:
               return 'Parsing error: Expression have defined both `definition` and `macro` property. Something one must be defined'
            if exp.get('definition') is None:
                if  exp.get('macro') is None:
                    return 'Parsing error: Expression `%s` have not defined `definition` or `macro` property' % exp['name']
                exp['definition'] = expand_macro()
            local_def = exp['definition']
            for k, v in define_directives.items():
                local_def = local_def.replace(k,v)
            exp['definition'] = local_def
            defs[exp['name']] = exp['definition']
            comment = exp.get('Description')
            tag = exp.get('tag')
            if tag is None:
                tag = self.currentSection
            command = exp.get('command')
            name = exp.get('name')
            self.expressions.append(exp)
            self.put_row(name,expression['definition'],command, comment, tag)
            for key in exp.keys():
                if key not in self.FIELDS_TO_SKIP:
                    varName = '%s%s%s' % (name,self.NAME_MAP['separator'],self.NAME_MAP[key])
                    self.put_row(varName,expression[key],'set', '', tag) 
            init_expression()
            return None
        def parse_val(text):
            if text == None:
                return ''
            return text.strip()
        def parse_define_directive(line):
            match = self.define_template.match(line)
            if match is None:
                raise SyntaxError('Invalid define specification')
            m = match.groupdict()
            define_key = m['key'].strip()
            define_val = m['val'].strip()
            if (define_key == '' or define_val == ''):
                print(line)
                raise SyntaxError('Invalid define specification')
            define_directives[define_key] = define_val
        current_field = None
        for line in text.splitlines():
            self.linenum = self.linenum + 1
            #print("%s %s" % (self.linenum, line))
            if (line.startswith('#define')):
                parse_define_directive(line)
                continue
            if line.strip()=='':
                continue
            if (line.startswith('#SECTION ')):
                self.currentSection = re.sub("#SECTION :?", "", line)
                continue
            match = self.line_template.match(line)
            if match is None:
                line = line.strip()
                if line == '---':
                    error = process_expression(expression)
                    if error is not None:
                        raise SyntaxError(error)
                    expression = {}
                    continue
                if current_field is not None:
                    if current_field == 'macro':
                        if len(self.macro) == 0:
                           self.macro.append(expression['macro']) 
                        param_match = self.param_template.match(line)
                        if param_match is None:
                            raise SyntaxError('Unexpected macro param format: "%s" for macro "%s"' % (line,self.macro[1]))
                        else:
                            self.macro.append(param_match.groupdict()['val'].strip())
                            continue            
                    else:     
                        expression[current_field] += ' ' + line
                        continue
                raise SyntaxError('Unexpected format')       
            m = match.groupdict()
            m['key'] = m['key'].strip()
            m['val'] = m['val'].strip()
            current_field = m['key']
            if m['key'] == 'set' or m['key'] == 'let':
                expression['name'] =  m['val']   
                expression['command'] = m['key']
            elif m['key'] in self.ALLOWED_TAGS:
                expression[m['key']] = m['val']
            else:
                if m['key'] == 'macro':
                    self.macro.append(m['val'])
                    expression['macro'] = self.macro
                else:
                    raise SyntaxError('Unexpected QlikView expression property: "%s"' % m['key'])
        error = process_expression(expression)
        if error is not None:
            raise SyntaxError(error)  
        return None
class QlikViewVariableExpander:
    expressions = []
    exp_dict = {}
    output = []
    not_found = set()
    VAR_PATTERN = re.compile('\\$\\((?P<key>[^=$][^())]+)\\)')
    def __init__(self, expressions):
        not_found = set()
        self.expressions = list(expressions)
        for exp in self.expressions:
            self.exp_dict[exp[1]] = exp[2]
    def expandAll(self):
        for exp in self.expressions:
            self.expandVariable(exp[1])
    def expandVariable(self, key):
        varToExpand = self.exp_dict[key]
        needToTestFuther = False
        for match in self.VAR_PATTERN.finditer(varToExpand):
            variable = match.groupdict()['key']
            if variable in self.exp_dict:
                replace_string = self.exp_dict[variable]
                varToExpand = varToExpand.replace('$(%s)' % variable, replace_string)
                needToTestFuther = True 
            else:
                print('Cannot find variable: %s in expression %s' % (variable,key))
        self.exp_dict[key] = varToExpand
        if needToTestFuther:
            self.expandVariable(key)
