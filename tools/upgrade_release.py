from pathlib import Path
from build import ROOT
p=ROOT/'site/index.html';s=p.read_text(encoding='utf8');old='<option value="missing">Required context identity is missing</option>';new=old+'<option value="undeclared">Negative control: dependency omitted from manifest</option>'
if 'value="undeclared"' not in s:s=s.replace(old,new)
p.write_text(s,encoding='utf8')
