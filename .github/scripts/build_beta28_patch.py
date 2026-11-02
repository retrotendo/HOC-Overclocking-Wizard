from pathlib import Path

def rep(s,a,b,n):
    if a not in s: raise SystemExit('beta28 missing '+n)
    return s.replace(a,b,1)

p=Path('Makefile');s=p.read_text();s=rep(s,'APP_VERSION := 0.1.0-beta.27','APP_VERSION := 0.1.0-beta.28','version');p.write_text(s)

p=Path('source/oc_config.hpp');s=p.read_text();s=rep(s,'LayoutInfo detect();\n','LayoutInfo detect();\n\nbool resetHocTuningToDefaults(std::string& error);\n','reset declaration');p.write_text(s)

p=Path('source/oc_config.cpp');s=p.read_text()
fn=r'''bool resetHocTuningToDefaults(std::string& error){
    std::array<u64,256> v{};bool old=false;const Idx*i=nullptr;
    if(!read(v,old,i,error))return false;
    // HOC performance defaults which can influence Wizard tests.
    v[5]=0;v[6]=0;v[7]=1785;v[8]=1963;v[9]=1;v[10]=70;
    if(old){
        // HOC 2.5.1: shared DVFS plus Auto High RAM CPU OC defaults.
        v[15]=1;v[16]=0;v[17]=0;v[18]=0;v[19]=0;v[20]=0;
        v[28]=0;v[29]=0;v[30]=1;v[31]=1683000ULL;v[32]=2666000ULL;
    }else{
        // Current HOC: separate GPU/CPU DVFS defaults.
        v[15]=1;v[16]=0;v[17]=1;v[18]=0;v[19]=0;v[20]=0;v[21]=0;v[22]=0;
        v[33]=0;v[34]=0;
    }
    // HOC uses 0 as Auto/default for KIP tuning entries. Reset the entire tuning
    // block: RAM/timings/latencies, CPU UV, GPU UV/custom table and SoC table.
    const int first=i->hp;
    const int last=i->socVolt0+int(sizeof(SOC_FREQS)/sizeof(SOC_FREQS[0]))-1;
    for(int n=first;n<=last;++n)v[n]=0;
    return write(v,error);
}

'''
s=rep(s,'bool setRamPreparation(',fn+'bool setRamPreparation(','reset implementation');p.write_text(s)

cfg=Path('source/oc_config.cpp').read_text();hdr=Path('source/oc_config.hpp').read_text()
checks={
 'version':'0.1.0-beta.28' in Path('Makefile').read_text(),
 'declaration':'resetHocTuningToDefaults' in hdr,
 'kip reset':'for(int n=first;n<=last;++n)v[n]=0' in cfg,
 'soc table reset':'i->socVolt0+int(sizeof(SOC_FREQS)/sizeof(SOC_FREQS[0]))-1' in cfg,
 'current dvfs defaults':'v[15]=1;v[16]=0;v[17]=1;v[18]=0' in cfg,
 '251 auto ram cpu defaults':'v[30]=1;v[31]=1683000ULL;v[32]=2666000ULL' in cfg,
}
for n,o in checks.items():print(('PASS ' if o else 'FAIL ')+n)
if not all(checks.values()):raise SystemExit('beta28 config audit failed')
