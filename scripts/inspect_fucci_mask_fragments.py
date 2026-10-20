#!/usr/bin/env python3
"""Inspect exact mask voxels and summarize fragmentation without changing any mask."""
from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fucci_mpl_cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage
import tifffile

from fucci_analysis.data import sha256, write_json

SELECTED = [("241016/14", "31", "Previously discussed: one large component and tiny satellites"),
            ("241016/14", "92", "Strongly fragmented example with little dominant support"),
            ("241016/14", "89", "Many components with a dominant but incomplete main component"),
            ("241016/1", "250", "Fragmented example from the second available mask"),
            ("241016/1", "201", "Three components; largest fraction near the dataset median among fragmented labels"),
            ("241016/1", "179", "Single-component example with volume near the dataset median for single-component labels")]


def fragmentation_summary(labels, mapping, out, figs):
    split = labels.n_components > 1
    children = mapping.merge(labels[["mask_label_id", "largest_object_id"]], on="mask_label_id", validate="many_to_one")
    other = children[children.object_id != children.largest_object_id]
    summary = {"original_mask_labels": len(labels), "source_components": len(mapping),
        "single_component_labels": int((~split).sum()), "multiple_component_labels": int(split.sum()),
        "single_component_fraction": float((~split).mean()),
        "median_components_among_fragmented": float(labels.loc[split, "n_components"].median()),
        "median_largest_volume_fraction_among_fragmented": float(labels.loc[split, "largest_component_fraction"].median()),
        "nonlargest_components": len(other), "nonlargest_components_at_most_8_voxels": int((other.volume <= 8).sum()),
        "nonlargest_tiny_fraction": float((other.volume <= 8).mean()), "median_nonlargest_volume_voxels": float(other.volume.median()),
        "unit": "Original segmentation labels; biological cell identity not verified"}
    for threshold in [.9, .95, .99, .999]:
        count = int((labels.loc[split, "largest_component_fraction"] >= threshold).sum())
        summary[f"fragmented_largest_at_least_{threshold}_count"] = count
        summary[f"fragmented_largest_at_least_{threshold}_fraction"] = count/int(split.sum())
    write_json(out / "fragmentation_summary.json", summary)
    rows=[]
    for field, group in labels.groupby("field_id"):
        multi=group[group.n_components>1]
        rows.append({"field_id":field,"labels":len(group),"single_component_labels":int((group.n_components==1).sum()),
                     "fragmented_labels":len(multi),"fragmented_largest_at_least_95_percent":int((multi.largest_component_fraction>=.95).sum()),
                     "fragmented_largest_at_least_99_percent":int((multi.largest_component_fraction>=.99).sum()),
                     "median_components_among_fragmented":multi.n_components.median()})
    pd.DataFrame(rows).to_csv(out / "fragmentation_by_fof.csv",index=False)
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),constrained_layout=True)
    counts=[summary['single_component_labels'],summary['multiple_component_labels']]
    axes[0].bar([0,1],counts,color=['#229b88','#c57539'])
    axes[0].set_xticks([0,1]);axes[0].set_xticklabels(['One component','Multiple components'])
    for i,n in enumerate(counts): axes[0].text(i,n+150,f'{n:,}\n{n/len(labels):.1%}',ha='center',fontsize=10)
    axes[0].set(ylabel='Original mask labels',title='All 21,653 original labels',ylim=(0,17000))
    values=labels.loc[split,'largest_component_fraction']*100
    axes[1].hist(values,bins=np.linspace(0,100,31),color='#229b88')
    axes[1].axvline(95,color='#b65a3b',ls='--',lw=1)
    axes[1].set(xlabel='Volume in largest component (%)',ylabel='Fragmented mask labels',title=f'Fragmented labels only (n={int(split.sum()):,})')
    axes[1].text(.03,.96,f'Median: {values.median():.1f}%\n63.8% have at least 95%\n41.5% have at least 99%',transform=axes[1].transAxes,va='top',fontsize=10)
    axes[2].hist(np.log10(other.volume),bins=40,color='#9b5279')
    axes[2].set(xlabel='log10(non-largest component volume, voxels)',ylabel='Components',title=f'Extra components (n={len(other):,})')
    axes[2].text(.97,.96,f'{summary["nonlargest_tiny_fraction"]:.1%} are 8 voxels or smaller\nMedian: 1 voxel',transform=axes[2].transAxes,ha='right',va='top',fontsize=10)
    fig.suptitle('How common are dominant components and small satellites? Counts cover all 31 FoFs')
    for suffix in ['png','pdf']: fig.savefig(figs/f'fragmentation_summary.{suffix}',dpi=180,bbox_inches='tight',facecolor='white')
    plt.close(fig)
    return summary


def png64(array):
    buffer=BytesIO();Image.fromarray(array).save(buffer,format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def inspect_label(mask, parent, mapping, reason):
    label=int(parent.CellposeLabel)
    start=np.maximum(0,np.array([parent.z_min,parent.y_min,parent.x_min],int)-3)
    stop=np.minimum(mask.shape,np.array([parent.z_max,parent.y_max,parent.x_max],int)+3)
    crop=mask[tuple(slice(a,b) for a,b in zip(start,stop))]
    components,n=ndimage.label(crop==label,structure=np.ones((3,3,3),dtype=bool))
    volumes=np.bincount(components.ravel())[1:]
    order=np.argsort(-volumes,kind='stable')+1
    lookup=np.zeros(n+1,dtype=np.int32);lookup[order]=np.arange(1,n+1)
    ranked=lookup[components]
    sizes=volumes[order-1]
    assert n==parent.n_components and int(sizes.sum())==int(parent.volume)
    expected=mapping.loc[mapping.mask_label_id==parent.mask_label_id,'volume'].to_numpy()
    np.testing.assert_array_equal(np.sort(sizes),np.sort(expected))
    palette=np.zeros((n+1,3),dtype=np.uint8)
    palette[1]=[24,188,164]
    if n>1: palette[2:]=(plt.get_cmap('plasma')(np.linspace(.2,.95,n-1))[:,:3]*255).astype(np.uint8)
    rgb=palette[ranked]
    rgb[(crop!=0)&(crop!=label)]=[42,45,50]
    extra=ranked.copy();extra[extra==1]=0
    projection=palette[ranked.max(axis=0)]
    projection[(crop>0).any(axis=0)&(ranked.max(axis=0)==0)]=[42,45,50]
    extra_projection=palette[extra.max(axis=0)]
    extra_projection[(ranked==1).any(axis=0)&(extra.max(axis=0)==0)]=[50,54,60]
    rows=[]
    for rank,size in enumerate(sizes,start=1):
        coords=np.argwhere(ranked==rank)+start
        z,y,x=coords.mean(axis=0)
        rows.append({'field_id':parent.field_id,'CellposeLabel':str(label),'component_rank_by_volume':rank,
                     'volume_voxels':int(size),'fraction_of_original_label':float(size/sizes.sum()),
                     'z_center':z,'y_center':y,'x_center':x,'z_min':int(coords[:,0].min()),'z_max_inclusive':int(coords[:,0].max()),
                     'touches_first_or_last_stack_slice':bool(((coords[:,0]==0)|(coords[:,0]==mask.shape[0]-1)).any())})
    main_counts=(ranked==1).sum(axis=(1,2));extra_counts=(ranked>1).sum(axis=(1,2))
    possible=[int(main_counts.argmax()),int(extra_counts.argmax()),int(np.quantile(np.flatnonzero((ranked>0).any(axis=(1,2))),.8))]
    slices=[]
    for z in possible+list(np.flatnonzero((ranked>0).any(axis=(1,2)))):
        if z not in slices: slices.append(z)
        if len(slices)==3:break
    while len(slices)<3:slices.append(slices[-1])
    return dict(parent=parent,ranked=ranked,colors=palette,rgb=rgb,projection=projection,
                extra_projection=extra_projection,sizes=sizes,start=start,stop=stop,rows=rows,slices=sorted(slices),reason=reason)


def detail_figure(item):
    p=item['parent'];sizes=item['sizes'];start=item['start'];stop=item['stop']
    fig,axes=plt.subplots(2,3,figsize=(14,10))
    extent=(start[2]-.5,stop[2]-.5,stop[1]-.5,start[1]-.5)
    axes[0,0].imshow(item['projection'],interpolation='nearest',extent=extent)
    axes[0,0].set_title('All components: XY projection\nSmall pieces drawn over larger ones',fontsize=10)
    axes[0,1].imshow(item['extra_projection'],interpolation='nearest',extent=extent)
    axes[0,1].set_title('Disconnected satellites highlighted\nLargest component shown in gray',fontsize=10)
    axes[0,2].bar(np.arange(1,len(sizes)+1),sizes,color=item['colors'][1:]/255)
    axes[0,2].set(yscale='log',ylim=(.7,max(sizes)*1.7),xlabel='Component rank (largest first)',ylabel='Voxels, log scale',
                  title=f'{len(sizes)} components; {sizes.sum():,} voxels total')
    axes[0,2].xaxis.set_major_locator(MaxNLocator(integer=True))
    axes[0,2].text(.97,.97,f'Largest: {sizes[0]:,} voxels ({sizes[0]/sizes.sum():.2%})\nOther {len(sizes)-1}: {sizes[1:].sum():,} voxels total',
                   transform=axes[0,2].transAxes,ha='right',va='top',fontsize=9)
    for col,z in enumerate(item['slices']):
        axes[1,col].imshow(item['rgb'][z],interpolation='nearest',extent=extent)
        axes[1,col].set_title(f'Actual slice z={z+start[0]}',fontsize=10)
    for ax in [axes[0,0],axes[0,1],*axes[1]]:
        ax.set_xlabel('X voxel index');ax.set_ylabel('Y voxel index')
    fig.suptitle(f'{p.field_id}: original Cellpose label {p.CellposeLabel}\n{item["reason"]}',fontsize=13)
    fig.legend(handles=[Patch(color='#18bca4',label='Largest 3D component'),Patch(color='#e76c56',label='Other components: warm/purple colors'),
                        Patch(color='#2a2d32',label='Other original labels in slice context')],loc='lower center',ncol=3,fontsize=9)
    fig.text(.5,.055,'26-neighbor connectivity in 3D; colors indicate components, not cell-cycle phases. Matching fluorescence images are unavailable.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.93),h_pad=3)
    return fig


def viewer(items,path,summary):
    records=[]
    for item in items:
        p=item['parent'];ranked=item['ranked'];colors=item['colors']
        fragments=ranked.copy();fragments[fragments==1]=0
        records.append({'name':f'{p.field_id}, mask {p.CellposeLabel}', 'reason':item['reason'],
            'z0':int(item['start'][0]),'initial':int((ranked==1).sum(axis=(1,2)).argmax()),
            'n':len(item['sizes']),'total':int(item['sizes'].sum()),'largest':int(item['sizes'][0]),
            'frames':[png64(frame) for frame in item['rgb']],
            'fragments':[png64(colors[frame]) for frame in fragments],
            'projection':png64(item['projection']),'extra_projection':png64(item['extra_projection']),
            'rows':item['rows']})
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><title>FUCCI mask component inspection</title>
<style>body{font:16px system-ui;margin:24px auto;max-width:1100px;padding:0 18px;background:#f5f7f9;color:#16222d}h1{font-size:26px}select,button,input{font:inherit;margin:6px;padding:6px}input[type=range]{width:55%;vertical-align:middle}.panels{display:grid;grid-template-columns:1fr 1fr;gap:20px}.panel{background:white;padding:15px;border:1px solid #cdd5da;border-radius:8px}.panel img{width:100%;height:380px;object-fit:contain;image-rendering:pixelated;background:#000}table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #ddd;padding:5px;text-align:right}th{background:#e7eef2}small{display:block;margin:12px 0}#stats{font-weight:600}.controls{background:#e7eef2;padding:10px} @media(max-width:700px){.panels{grid-template-columns:1fr}.panel img{height:300px}}</style>
<h1>Disconnected components in the original FUCCI masks</h1>
<p>Choose a label and move through its actual z slices. Turquoise is the largest component; warm/purple colors mark the other components. Gray in slice context belongs to other original labels.</p>
<label>Example <select id="example"></select></label><p id="reason"></p><p id="stats"></p>
<div class="controls"><button id="previous">Previous slice</button><button id="play">Play</button><button id="next">Next slice</button><br><label>Slice <input id="slice" type="range" min="0" step="1"><strong id="z"></strong></label><label><input id="satellites" type="checkbox">Only smaller components</label></div>
<div class="panels"><div class="panel"><h2>XY projection over all z slices</h2><img id="projection" alt="Projection of all components"></div><div class="panel"><h2>One actual z slice</h2><img id="plane" alt="Selected slice"></div></div>
<small>Projections can overlap disconnected pieces. Use the slice control to inspect them. Components use 26-neighbor 3D connectivity. Coordinates are voxel indices; physical z spacing is not applied. No mask voxels were edited. These two FoFs have no locally available matching fluorescence images.</small>
<h2>Component sizes and positions</h2><table><thead><tr><th>Rank</th><th>Voxels</th><th>Fraction</th><th>Z range</th><th>Touches stack boundary</th></tr></thead><tbody id="sizes"></tbody></table>
<script>const data=__DATA__; const $=id=>document.getElementById(id); let timer=null;
function current(){return data[Number($('example').value)];}
function draw(){const d=current(),i=Number($('slice').value),small=$('satellites').checked;$('plane').src='data:image/png;base64,'+(small?d.fragments[i]:d.frames[i]);$('projection').src='data:image/png;base64,'+(small?d.extra_projection:d.projection);$('z').textContent='z='+String(d.z0+i);}
function stop(){if(timer!==null)clearInterval(timer);timer=null;$('play').textContent='Play';}
function select(){stop();const d=current();$('slice').max=d.frames.length-1;$('slice').value=d.initial;$('reason').textContent=d.reason;$('stats').textContent=d.n+' components; '+d.total.toLocaleString()+' voxels; largest component: '+(100*d.largest/d.total).toFixed(2)+'%';$('sizes').innerHTML=d.rows.map(r=>'<tr><td>'+r.component_rank_by_volume+'</td><td>'+r.volume_voxels+'</td><td>'+(100*r.fraction_of_original_label).toFixed(3)+'%</td><td>'+r.z_min+'–'+r.z_max_inclusive+'</td><td>'+(r.touches_first_or_last_stack_slice?'Yes':'No')+'</td></tr>').join('');draw();}
function advance(step){const n=current().frames.length;$('slice').value=(Number($('slice').value)+step+n)%n;draw();}
data.forEach((d,i)=>{const option=document.createElement('option');option.value=i;option.textContent=d.name;$('example').appendChild(option);});
$('example').onchange=select;$('slice').oninput=draw;$('satellites').onchange=draw;$('previous').onclick=()=>{stop();advance(-1);};$('next').onclick=()=>{stop();advance(1);};$('play').onclick=()=>{if(timer!==null){stop();}else{timer=setInterval(()=>advance(1),250);$('play').textContent='Pause';}};select();</script></html>'''
    path.write_text(html.replace('__DATA__',json.dumps(records,separators=(',',':'))))


def main():
    repo=Path(__file__).resolve().parents[1]
    source=repo/'results/fucci_classification'
    out=source/'fragment_inspection';out.mkdir(exist_ok=True)
    figs=repo/'figs4paper/fucci_classification/fragment_inspection';figs.mkdir(exist_ok=True)
    labels=pd.read_csv(source/'mask_label_measurements.csv.gz',dtype={'CellposeLabel':str})
    mapping=pd.read_csv(source/'object_mapping.csv.gz')
    inventory=pd.read_csv(source/'image_inventory.csv')
    summary=fragmentation_summary(labels,mapping,out,figs)
    items=[];sources=[]
    for field in dict.fromkeys(t[0] for t in SELECTED):
        record=inventory.loc[inventory.field_id==field].iloc[0]
        assert sha256(Path(record.mask_path))==record.mask_sha256
        mask=tifffile.imread(record.mask_path)
        sources.append({'field_id':field,'path':record.mask_path,'sha256':record.mask_sha256,'shape':list(mask.shape)})
        for f,label,reason in SELECTED:
            if f!=field:continue
            parent=labels.loc[(labels.field_id==f)&(labels.CellposeLabel==label)].iloc[0]
            items.append(inspect_label(mask,parent,mapping,reason))
        del mask
    items.sort(key=lambda item:next(i for i,(field,label,_) in enumerate(SELECTED) if field==item['parent'].field_id and label==item['parent'].CellposeLabel))
    component_rows=[];index=[]
    with PdfPages(figs/'mask_component_details.pdf') as pdf:
        for page,item in enumerate(items,start=1):
            p=item['parent'];name=f'{p.field_id.replace("/","_")}_mask_{p.CellposeLabel}'
            fig=detail_figure(item);pdf.savefig(fig);fig.savefig(figs/f'{name}.png',dpi=180,facecolor='white');plt.close(fig)
            component_rows.extend(item['rows'])
            index.append({'field_id':p.field_id,'CellposeLabel':p.CellposeLabel,'pdf_page':page,'png':f'{name}.png','reason':item['reason'],
                          'components':len(item['sizes']),'volume':int(item['sizes'].sum()),'largest_fraction':float(item['sizes'][0]/item['sizes'].sum())})
    pd.DataFrame(component_rows).to_csv(out/'component_details.csv',index=False)
    pd.DataFrame(index).to_csv(out/'inspection_index.csv',index=False)
    viewer(items,figs/'mask_component_viewer.html',summary)
    write_json(out/'provenance.json',{'masks':sources,'selected_labels':index,'connectivity':26,'no_mask_voxels_changed':True,
        'component_counts_and_volumes_match_export':True,'selection':'Four deliberately fragmented examples, one example near median fragmented geometry, one single-component example',
        'script_sha256':sha256(Path(__file__))})
    text=f'''# FUCCI mask-fragment inspection

## Does a dominant component plus tiny pieces describe most labels?

Of all **21,653 original mask labels**, **13,981 (64.6%) have one connected component**. The remaining **7,672 (35.4%) have multiple components**. These are segmentation labels, not confirmed biological cells.

Among multi-component labels:

- **4,896 (63.8%)** have at least 95% of their volume in the largest component.
- **3,185 (41.5%)** have at least 99% in the largest component.
- The median largest-component fraction is **98.2%**; the median number of components is **3**.

Of the **26,822 non-largest components**, **24,604 (91.7%) contain eight voxels or fewer**; their median size is **one voxel**. Eight voxels is a descriptive threshold, not an adopted exclusion rule. Thus tiny satellites are common among fragmented labels, while the example with 28 components is more fragmented than typical. A large component plus satellites is not the geometry of the majority of all labels, because most have just one component.

## Inspect the actual masks

- [Interactive slice viewer](../figs4paper/fucci_classification/fragment_inspection/mask_component_viewer.html): open the local HTML file in a browser, choose an example, drag the z slider, or play the slices. Toggle smaller components to see satellites separately. The viewer is self-contained and needs no network.
- [Six detailed inspection pages (PDF)](../figs4paper/fucci_classification/fragment_inspection/mask_component_details.pdf)
- [Fragmentation summary across all 31 FoFs](../figs4paper/fucci_classification/fragment_inspection/fragmentation_summary.png)

The detailed figures show projections, actual z slices, and every component's voxel count. Turquoise denotes the largest 3D component; warm/purple colors denote smaller components, with stable colors across slices. Gray shows context from other labels (or the main component in the satellite projection). Projections can hide or superimpose disconnected pieces; the slice viewer resolves the z dimension. Component ranks are local to an example and are not the source ObjectNumber.

Only the two available original masks, FoFs 1 and 14 of acquisition 241016, are visualized. Their checksums match the previous audit, and every selected label's component count and individual component volumes match the exported table. No mask voxel or supplied class label was changed. Matching fluorescence images are unavailable for these two FoFs; these figures establish mask geometry but cannot independently determine whether each disconnected piece belongs to a real nucleus.

Four examples were deliberately selected for fragmentation, so they do not estimate its prevalence. The additional three-component example has a dominant fraction close to the median across fragmented labels; the single-component example has a volume close to the median across all single-component labels. The prevalence statistics use every label across all 31 FoFs.

## Reproduce

```bash
python scripts/inspect_fucci_mask_fragments.py
```

Counts, component coordinates, page mappings, and mask provenance are saved under `results/fucci_classification/fragment_inspection`.
'''
    (repo/'docs/fucci_mask_fragment_inspection.md').write_text(text)
    print(json.dumps(summary,indent=2))
    print(f'Wrote {len(items)} detailed pages and the interactive viewer to {figs}')


if __name__=='__main__':main()
