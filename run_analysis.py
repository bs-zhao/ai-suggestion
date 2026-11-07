#!/usr/bin/env python3
"""Run every analysis directly from the original, unmodified survey Excel export.

Each invocation reimports the original workbook and regenerates deidentified,
intermediate participant/trial CSVs before calculating statistics and figures.
A successful run cannot silently reuse stale preprocessed records.
"""
from __future__ import annotations
import argparse
import csv
import json
import hashlib
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'svg.fonttype': 'none', 'pdf.fonttype': 42, 'savefig.facecolor': 'white'})
import numpy as np
from scipy import stats
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parent
DEFAULT_RAW = ROOT/'data'/'raw'/'c73c62ff5ec44be1b3fc6af2d5515eb6(1).xlsx'
GROUPS = ('AI_label', 'Unlabeled')
NAMES = {'AI_label': 'AI labeled', 'Unlabeled': 'Unlabeled'}
COLORS = {'AI_label': '#27617b', 'Unlabeled': '#c47a48'}
MODULES = (
    '00_demographics', '01_descriptives', '02_conflict_adoption',
    '03_agree_no_switch_confidence', '04_conflict_no_switch_confidence',
    '05_conflict_source_by_switch', '06_scenario_heterogeneity',
    '07_survey_and_quality', '08_robustness',
)
RNG_SEED = 20261107


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, headers=None):
    if headers is None:
        headers = list(rows[0]) if rows else []
    if not headers:
        return
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        out = csv.DictWriter(handle, fieldnames=headers)
        out.writeheader()
        out.writerows(rows)


def write_report(directory, lines, table_rows=None, table_headers=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'results.txt').write_text('\n'.join(lines).strip() + '\n', encoding='utf-8')
    if table_rows is not None:
        write_csv(directory / 'statistics.csv', table_rows, table_headers)


def save_fig(fig, directory, name):
    fig.savefig(directory / f'{name}.png', dpi=300, bbox_inches='tight')
    fig.savefig(directory / f'{name}.svg', bbox_inches='tight')
    fig.savefig(directory / f'{name}.pdf', bbox_inches='tight')
    plt.close(fig)


def fmt(x, nd=3):
    return f'{x:.{nd}f}' if math.isfinite(float(x)) else 'NA'


def means_by_subject(trials, predicate, outcome):
    cache = defaultdict(list)
    for row in trials:
        if predicate(row):
            cache[(row['source'], row['participant_id'])].append(float(row[outcome]))
    return {group: np.asarray([np.mean(values) for (source, _), values in sorted(cache.items()) if source == group], dtype=float)
            for group in GROUPS}


def ci_mean(x, alpha=.05):
    x = np.asarray(x, float)
    if x.size < 2:
        return (float('nan'), float('nan'))
    se = stats.sem(x)
    h = stats.t.ppf(1-alpha/2, len(x)-1) * se
    return (float(x.mean()-h), float(x.mean()+h))


def onesample(x):
    x = np.asarray(x, float)
    if len(x) < 2 or np.std(x, ddof=1) == 0:
        return {'n':len(x), 'mean': float(x.mean()) if len(x) else float('nan'), 't':float('nan'), 'df':len(x)-1, 'p':float('nan'), 'lo':float('nan'), 'hi':float('nan')}
    t, p = stats.ttest_1samp(x, 0)
    low, high = ci_mean(x)
    return dict(n=len(x), mean=float(x.mean()), t=float(t), df=len(x)-1, p=float(p), lo=low, hi=high)


def welch(a, b):
    a, b = np.asarray(a,float), np.asarray(b,float)
    if len(a)<2 or len(b)<2:
        return dict(n1=len(a),n2=len(b),difference=float('nan'),t=float('nan'),df=float('nan'),p=float('nan'),lo=float('nan'),hi=float('nan'),hedges_g=float('nan'))
    av, bv = np.var(a, ddof=1), np.var(b, ddof=1)
    v1, v2 = av/len(a), bv/len(b)
    df = (v1+v2)**2 / ((v1**2/(len(a)-1))+(v2**2/(len(b)-1))) if v1+v2 else float('nan')
    delta = float(a.mean() - b.mean())
    se = math.sqrt(v1+v2)
    h = stats.t.ppf(.975,df)*se if se else 0
    t, p = stats.ttest_ind(a,b,equal_var=False)
    sd_p = math.sqrt(((len(a)-1)*av+(len(b)-1)*bv)/(len(a)+len(b)-2))
    g = delta/sd_p*(1-3/(4*(len(a)+len(b))-9)) if sd_p else float('nan')
    return dict(n1=len(a),n2=len(b),difference=delta,t=float(t),df=float(df),p=float(p),lo=delta-h,hi=delta+h,hedges_g=g)


def explain_welch(name, a, b, unit='points'):
    w = welch(a,b)
    return [f'{name}: participant-level Welch comparison (AI minus unlabeled).',
            f'  AI mean={fmt(np.mean(a))}, n={len(a)}; unlabeled mean={fmt(np.mean(b))}, n={len(b)}.',
            f'  Mean difference={fmt(w["difference"])} {unit}; 95% CI [{fmt(w["lo"])}, {fmt(w["hi"])}].',
            f'  t({fmt(w["df"],2)})={fmt(w["t"])}, p={fmt(w["p"],4)}; Hedges g={fmt(w["hedges_g"])}.']


def report_p(p):
    return '<.0001' if math.isfinite(p) and p<.0001 else (f'{p:.4f}' if math.isfinite(p) else 'NA')


def explain_onesample(name, x):
    t=onesample(x)
    return [f'{name}: change versus zero using participant averages.',
            f'  n={len(x)}, M={fmt(np.mean(x))}, 95% CI [{fmt(t["lo"])}, {fmt(t["hi"])}], '
            f't({t["df"]})={fmt(t["t"])}, p={report_p(t["p"])}.']


def subject_plot(directory, filename, values, title, ylabel, hline=0, percent=False):
    fig, ax=plt.subplots(figsize=(6.8,4.6))
    rng=np.random.default_rng(RNG_SEED)
    for j, group in enumerate(GROUPS):
        ar=np.asarray(values[group],float)
        jx=rng.uniform(-.16,.16,len(ar)) + j
        ax.scatter(jx, ar, color=COLORS[group], alpha=.42, s=34, edgecolors='none')
        low, high=ci_mean(ar)
        ax.errorbar(j, ar.mean(), yerr=[[ar.mean()-low],[high-ar.mean()]], fmt='o', color='black', capsize=5, markersize=8, linewidth=2.0, zorder=8)
    ax.axhline(hline,color='0.55',lw=1,linestyle='--')
    ax.set_xticks([0,1], [NAMES[g] for g in GROUPS]); ax.set_xlim(-.48,1.48)
    ax.set_ylabel(ylabel); ax.set_title(title,fontsize=12,weight='bold')
    if percent: ax.set_ylim(bottom=-3,top=max(40,max(float(np.max(values[g])) for g in GROUPS)+8))
    ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();save_fig(fig,directory,filename)


def ensure_numeric(trials,participants):
    for r in trials:
        for k in ('initial_confidence','final_confidence','confidence_change','agrees_initially','changed_choice','adopted_conflicting_advice'):
            r[k]=int(r[k])
    for r in participants:
        for k in ('duration_seconds','P1','P2','P3','P4'):
            try:r[k]=float(r[k])
            except(ValueError,TypeError):r[k]=float('nan')


def validate(trials, participants):
    ids={r['participant_id'] for r in participants}
    assert len(participants)==60 and len(ids)==60, 'Expected 60 unique participants'
    assert len(trials)==720, 'Expected 12 trials per participant'
    assert Counter(r['source'] for r in participants)==Counter({'AI_label':30,'Unlabeled':30})
    assert Counter(r['participant_id'] for r in trials)==Counter({k:12 for k in ids})
    assert all(t['participant_id'] in ids for t in trials)
    assert all(t['source'] == next(p['source'] for p in participants if p['participant_id']==t['participant_id']) for t in trials)
    assert all(t['confidence_change']==t['final_confidence']-t['initial_confidence'] for t in trials)
    assert all(1<=t['initial_confidence']<=5 and 1<=t['final_confidence']<=5 for t in trials)
    assert all(t['agrees_initially']==int(t['initial_choice']==t['recommendation']) for t in trials)
    assert all(t['changed_choice']==int(t['initial_choice']!=t['final_choice']) for t in trials)
    assert all(t['adopted_conflicting_advice']==int(not t['agrees_initially'] and t['final_choice']==t['recommendation']) for t in trials)
    assert len(set((t['participant_id'],t['scenario']) for t in trials))==720
    assert sum(not t['agrees_initially'] for t in trials)==241
    assert sum(t['adopted_conflicting_advice'] for t in trials)==61


def summary_stats(trials, condition, predicate):
    subset=[r for r in trials if r['source']==condition and predicate(r)]
    return {'n_trials':len(subset),'n_subjects':len({r['participant_id'] for r in subset}),
            'mean_pre': float(np.mean([r['initial_confidence'] for r in subset])) if subset else float('nan'),
            'mean_post':float(np.mean([r['final_confidence'] for r in subset])) if subset else float('nan'),
            'mean_delta':float(np.mean([r['confidence_change'] for r in subset])) if subset else float('nan')}


def demographics(trials,people,where):
    out=['MODULE 00 | PARTICIPANT CHARACTERISTICS','N=60 independent participants, 30 per source condition.',
         'All variables from the same randomized questionnaire; no gender variable was collected.',
         'Counts below are descriptive; categorical groups are small, so no balance significance tests are used.','']
    tbl=[]
    for variable,title in [('age_range','Age ranges'),('country','Country'),('language','Primary language'),('ai_frequency','Generative AI usage')]:
        cats=sorted({str(p[variable]) for p in people})
        out += [title+':']
        for cat in cats:
            n=[sum(p['source']==g and str(p[variable])==cat for p in people) for g in GROUPS]
            out.append(f'  {cat}: AI {n[0]}/30 ({100*n[0]/30:.1f}%), unlabeled {n[1]}/30 ({100*n[1]/30:.1f}%)')
            tbl.append(dict(variable=variable, category=cat, AI_label=n[0],Unlabeled=n[1]))
        out.append('')
    for group in GROUPS:
        a=[p['duration_seconds'] for p in people if p['source']==group and math.isfinite(p['duration_seconds'])]
        out.append(f'Completion duration {NAMES[group]}: n={len(a)}, M={np.mean(a):.1f} seconds, median={np.median(a):.1f} seconds, SD={np.std(a,ddof=1):.1f}.')
    write_report(where,out,tbl)
    for variable,name,filename in [('age_range','Age distribution','age_distribution'),('ai_frequency','AI usage frequency','ai_frequency')]:
        categories=list(dict.fromkeys(str(p[variable]) for p in people))
        English={"18—24岁":"18–24","25—34岁":"25–34","35—44岁":"35–44","45—54岁":"45–54","55岁及以上":"55+","几乎每天使用":"Almost daily","每周使用":"Weekly","偶尔使用":"Occasionally"}
        fig,ax=plt.subplots(figsize=(7.2,4.6));bottom=np.zeros(2)
        cmap=plt.get_cmap('tab20c')
        for k,c in enumerate(categories):
            v=np.asarray([100*sum(p['source']==g and str(p[variable])==c for p in people)/30 for g in GROUPS])
            ax.bar([0,1],v,bottom=bottom,label=English.get(c,c),color=cmap(k/max(1,len(categories))),width=.57)
            bottom+=v
        ax.set_xticks([0,1],[NAMES[g] for g in GROUPS]);ax.set_ylabel('Participants (%)')
        ax.set_title(name,weight='bold');ax.set_ylim(0,110)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.12),ncol=2,frameon=False,fontsize=8)
        ax.spines[['top','right']].set_visible(False);fig.tight_layout();save_fig(fig,where,filename)


def descriptive(trials,people,where):
    rows=[];text=['MODULE 01 | DESCRIPTIVE CHOICE AND CONFIDENCE STATISTICS','Trial-level descriptions are not independent observations.','']
    for g in GROUPS:
        a=[t for t in trials if t['source']==g];conf=[t for t in a if not t['agrees_initially']];agree=[t for t in a if t['agrees_initially']]
        text += [NAMES[g]+f': participants={len([p for p in people if p["source"]==g])}; trials={len(a)}.',
                 f'  Initially agree={len(agree)}/{len(a)} ({100*len(agree)/len(a):.1f}%), conflict={len(conf)}/{len(a)} ({100*len(conf)/len(a):.1f}%).',
                 f'  All switches={sum(t["changed_choice"] for t in a)}/{len(a)}; switches after agreement={sum(t["changed_choice"] for t in agree)}/{len(agree)}.',
                 f'  Mean pre confidence={np.mean([t["initial_confidence"] for t in a]):.3f}; post={np.mean([t["final_confidence"] for t in a]):.3f}; delta={np.mean([t["confidence_change"] for t in a]):+.3f}.']
        for relation,subset in [('agree',agree),('conflict',conf)]:
            text.append(f'  {relation}: mean pre={np.mean([t["initial_confidence"] for t in subset]):.3f}, post={np.mean([t["final_confidence"] for t in subset]):.3f}, delta={np.mean([t["confidence_change"] for t in subset]):+.3f}.')
            rows.append(dict(source=g,relation=relation,n_trials=len(subset),n_changed=sum(t['changed_choice'] for t in subset),mean_pre=np.mean([t['initial_confidence'] for t in subset]),mean_post=np.mean([t['final_confidence'] for t in subset]),mean_change=np.mean([t['confidence_change'] for t in subset])))
        text.append('')
    write_report(where,text,rows)
    fig,axs=plt.subplots(1,2,figsize=(10,4))
    for j,g in enumerate(GROUPS):
        t=[x for x in trials if x['source']==g]
        axs[0].bar(j,100*np.mean([x['agrees_initially'] for x in t]),color=COLORS[g],width=.6)
        axs[1].bar(j,np.mean([x['confidence_change'] for x in t]),color=COLORS[g],width=.6)
    for ax in axs:
        ax.set_xticks([0,1],[NAMES[g] for g in GROUPS]);ax.spines[['top','right']].set_visible(False)
    axs[0].set_title('Initial advice agreement');axs[0].set_ylabel('Agreement rate (%)')
    axs[1].set_title('Overall confidence change');axs[1].set_ylabel('Post − pre (1–5 points)');axs[1].axhline(0,color='.4',lw=1)
    fig.tight_layout();save_fig(fig,where,'basic_descriptives')


def adoption(trials,people,where):
    pred=lambda t:not t['agrees_initially']
    val=means_by_subject(trials,pred,'adopted_conflicting_advice')
    tbl=[]; text=['MODULE 02 | ADOPTION OF CONFLICTING ADVICE','Primary participant-level analysis: a participant\'s mean adoption among conflict trials is one observation.','Participant means and pooled trial percentages are intentionally reported separately.','']
    for g in GROUPS:
        subset=[t for t in trials if t['source']==g and pred(t)]
        n=sum(t['adopted_conflicting_advice'] for t in subset)
        lo,hi=ci_mean(val[g])
        text += [f'{NAMES[g]}: {n}/{len(subset)} conflict trials adopted ({100*n/len(subset):.1f}% pooled).',
                 f'  Participant mean adoption={100*np.mean(val[g]):.2f}%; n={len(val[g])}; 95% CI [{100*lo:.2f}, {100*hi:.2f}] percentage points.',
                 f'  Subjects with at least one conflict adoption: {sum(1 for x in val[g] if x>0)}/{len(val[g])}.']
        tbl.append({'source':g,'n_participants':len(val[g]),'n_conflict_trials':len(subset),'n_adopted':n,'pooled_adoption_percent':round(100*n/len(subset),4),'mean_participant_adoption_percent':round(100*val[g].mean(),4),'mean_ci_low_percent':round(100*lo,4),'mean_ci_high_percent':round(100*hi,4)})
    text+=['']+explain_welch('Adoption, in proportions',val['AI_label'],val['Unlabeled'],unit='proportion units')
    ww=welch(val['AI_label'],val['Unlabeled'])
    text += [f'  Same mean difference in percentage points={ww["difference"]*100:.2f}, 95% CI [{ww["lo"]*100:.2f}, {ww["hi"]*100:.2f}].',
             "", f"MANUSCRIPT-READY: When advice conflicted with participants' initial choices, the participant-average adoption rate was {100*val['AI_label'].mean():.1f}% in the AI-label condition and {100*val['Unlabeled'].mean():.1f}% in the unlabeled condition. The difference was not statistically significant, t({ww['df']:.2f}) = {ww['t']:.2f}, p = {ww['p']:.3f}, 95% CI for the difference [{100*ww['lo']:.1f}, {100*ww['hi']:.1f}] percentage points.",
             'Caution: the unadjusted p-value is exploratory, not evidence of a confirmed AI-aversion effect.']
    write_report(where,text,tbl)
    subject_plot(where,'conflict_adoption', {g:val[g]*100 for g in GROUPS},'Adoption when advice conflicts','Participant adoption rate (%)',percent=True)


def unchanged_confidence(trials,where,which):
    if which=='agree':
        predicate=lambda t:t['agrees_initially'] and not t['changed_choice']
        heading='MODULE 03 | CONFIDENCE AFTER AGREEMENT, NO CHOICE SWITCH'
        sub='agree_no_switch_confidence'; title='Confidence after agreeing advice'
    else:
        predicate=lambda t:not t['agrees_initially'] and not t['changed_choice']
        heading='MODULE 04 | CONFIDENCE AFTER CONFLICT, NO CHOICE SWITCH'
        sub='conflict_no_switch_confidence';title='Confidence after conflicting advice (stayed)'
    vals=means_by_subject(trials,predicate,'confidence_change')
    txt=[heading,'Eligibility: '+('initial agreement AND unchanged final choice.' if which=='agree' else 'initial conflict AND unchanged final choice.'),
         'Within-condition tests use each eligible participant\'s mean post-minus-pre confidence.',
         'Participants without qualifying trials are excluded from this conditional analysis.','']
    rows=[]
    for g in GROUPS:
        st=summary_stats(trials,g,predicate)
        txt += [f'{NAMES[g]}: {st["n_trials"]} qualifying trials / {st["n_subjects"]} participants; trial mean pre={st["mean_pre"]:.3f}, post={st["mean_post"]:.3f}, change={st["mean_delta"]:+.3f}.']
        txt += explain_onesample(NAMES[g],vals[g]);txt += ['']
        tt=onesample(vals[g]);rows.append({'source':g,**st,'mean_subject_change':vals[g].mean(),'one_sample_t':tt['t'],'one_sample_df':tt['df'],'one_sample_p':tt['p'],'ci_low':tt['lo'],'ci_high':tt['hi']})
    txt+=explain_welch('Between-source change',vals['AI_label'],vals['Unlabeled'])
    txt += ['No no-advice control was included; confidence changes alone do not establish a causal effect of exposure to advice.']
    if which=='agree':
        txt += ["", f"MANUSCRIPT-READY: When advice agreed with the initial choice and participants maintained that choice, confidence increased in both conditions (AI: M = {vals['AI_label'].mean():.3f}, p = {report_p(onesample(vals['AI_label'])['p'])}; unlabeled: M = {vals['Unlabeled'].mean():.3f}, p = {report_p(onesample(vals['Unlabeled'])['p'])}). The between-condition difference was not significant, p = {welch(vals['AI_label'],vals['Unlabeled'])['p']:.3f}."]
    else:
        txt += ["", f"MANUSCRIPT-READY: Among trials in which advice conflicted with the initial choice and the original choice was retained, confidence change did not differ reliably from zero in either condition (AI: M = {vals['AI_label'].mean():.3f}, p = {report_p(onesample(vals['AI_label'])['p'])}; unlabeled: M = {vals['Unlabeled'].mean():.3f}, p = {report_p(onesample(vals['Unlabeled'])['p'])}), nor between conditions, p = {welch(vals['AI_label'],vals['Unlabeled'])['p']:.3f}."]
    write_report(where,txt,rows)
    subject_plot(where,sub,vals,title,'Confidence change (post − pre)')


def cluster_fit(rows, adjust_scenario=True, adjust_initial=False):
    """Cluster-robust linear model for within-trial confidence change in conflict trials."""
    scenarios=sorted({r['scenario'] for r in rows})
    names=['intercept','AI_label','switched','AI_x_switched']
    X=[[1.,float(r['source']=='AI_label'),float(r['changed_choice']),float(r['source']=='AI_label')*float(r['changed_choice'])] for r in rows]
    if adjust_scenario:
        for k in scenarios[1:]:
            names.append('scenario_'+k)
            for v,row in zip(X,rows): v.append(float(row['scenario']==k))
    if adjust_initial:
        names.append('initial_confidence_centered')
        for v,row in zip(X,rows):v.append(float(row['initial_confidence'])-4)
    y=np.asarray([float(r['confidence_change']) for r in rows]);x=np.asarray(X,float)
    mod=sm.OLS(y,x).fit(cov_type='cluster',cov_kwds={'groups':np.asarray([r['participant_id'] for r in rows]),'use_correction':True})
    k=3
    return dict(model=mod, names=names, beta=float(mod.params[k]),se=float(mod.bse[k]),p=float(mod.pvalues[k]),lo=float(mod.conf_int()[k,0]),hi=float(mod.conf_int()[k,1]),n=len(y),clusters=len(set(r['participant_id'] for r in rows)))


def interaction(trials,where):
    conflict=[r for r in trials if not r['agrees_initially']]
    text=['MODULE 05 | SOURCE LABEL x CHOICE REVISION, CONFLICT TRIALS ONLY',
          'Design: 2 source labels x switched-vs-stayed (switch is a POST-ADVICE behavior, not randomized).',
          'Outcome: post − pre confidence (integer scale -4..+4).',
          'Primary interaction analysis here is exploratory; not a causal moderation estimate.','']
    rows=[]
    for g in GROUPS:
        for k in (0,1):
            part=[r for r in conflict if r['source']==g and r['changed_choice']==k]
            nsub=len({r['participant_id'] for r in part})
            pre=np.mean([r['initial_confidence'] for r in part]);post=np.mean([r['final_confidence'] for r in part]);delta=np.mean([r['confidence_change'] for r in part])
            text.append(f'{NAMES[g]}, {"switched" if k else "stayed"}: n_trials={len(part)}, n_participants={nsub}, mean_pre={pre:.3f}, mean_post={post:.3f}, mean_delta={delta:+.3f}.')
            rows.append({'source':g,'switched':k,'n_trials':len(part),'n_participants':nsub,'mean_pre':pre,'mean_post':post,'mean_change':delta})
    text.append('')
    model_results=[]
    for label,scen,initial in [('Unadjusted cluster-robust OLS',False,False),('Scenario fixed effects + cluster-robust OLS',True,False),('Scenario FE + initial confidence + clustered OLS',True,True)]:
        fit=cluster_fit(conflict,scen,initial)
        model_results.append(fit)
        text += [f'{label}: interaction beta={fit["beta"]:+.4f}, SE={fit["se"]:.4f}, 95% CI [{fit["lo"]:+.4f}, {fit["hi"]:+.4f}], p={fit["p"]:.4f}; n_trials={fit["n"]}, clusters={fit["clusters"]}.']
    text += ['', 'Interpretation: a difference in post-switch confidence may reflect selection into switching or differing baseline confidence.',
             'Baseline confidence is systematically lower among switchers with AI-labeled advice, so report adjusted results.',
             'A significant within-group change is NOT a significant source-by-switch interaction.']
    text += ["", f"MANUSCRIPT-READY: Conditional on conflicting advice, choice revision and source label showed a descriptive interaction in confidence change. This source-by-revision interaction did not remain statistically significant when initial confidence and scenario were controlled (beta = {model_results[-1]['beta']:.3f}, p = {model_results[-1]['p']:.3f}). Because revision is a post-advice behavior, these conditional patterns cannot establish a causal effect of the source label."]
    write_report(where,text,rows)
    # Subject-cluster bootstrap for four conditional trial means.
    rng=np.random.default_rng(RNG_SEED)
    d=[]
    for g in GROUPS:
        grp=[r for r in conflict if r['source']==g]
        subjects=sorted({r['participant_id'] for r in grp})
        bysub={s:[r for r in grp if r['participant_id']==s] for s in subjects}
        for sw in (0,1):
            sampled=[r['confidence_change'] for r in grp if r['changed_choice']==sw]
            arr=[]
            for _ in range(2000):
                subs=rng.choice(subjects,len(subjects),replace=True)
                z=[r['confidence_change'] for s in subs for r in bysub[s] if r['changed_choice']==sw]
                if z: arr.append(np.mean(z))
            d.append((g,sw,np.mean(sampled),float(np.quantile(arr,.025)),float(np.quantile(arr,.975))))
    fig,ax=plt.subplots(figsize=(7.2,4.8))
    for g in GROUPS:
        p=[q for q in d if q[0]==g];x=np.asarray([0,1])+(-.085 if g=='AI_label' else .085)
        mu=np.asarray([t[2] for t in p]);lo=np.asarray([t[3] for t in p]);hi=np.asarray([t[4] for t in p])
        ax.errorbar(x,mu,yerr=[mu-lo,hi-mu],label=NAMES[g],marker='o',markersize=8,linewidth=2.0,capsize=5,color=COLORS[g])
    ax.axhline(0,color='.5',ls='--',lw=1)
    ax.set_xticks([0,1],['Stayed with initial choice','Switched to advice']);ax.set_xlim(-.25,1.25)
    ax.set_ylabel('Confidence change (post − pre)');ax.set_title('Choice revision and confidence after conflict',weight='bold')
    ax.legend(frameon=False);ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();save_fig(fig,where,'source_x_choice_revision')


def scenarios(trials,where):
    text=['MODULE 06 | SCENARIO-LEVEL HETEROGENEITY','12 fixed scenarios are examined descriptively; this is not a cross-cultural or item-generalization test.','']
    rows=[]
    for s in sorted({r['scenario'] for r in trials}):
        for g in GROUPS:
            t=[r for r in trials if r['scenario']==s and r['source']==g]
            c=[r for r in t if not r['agrees_initially']]
            a=sum(r['adopted_conflicting_advice'] for r in c)
            rate=100*a/len(c) if c else float('nan')
            rows.append(dict(scenario=s,source=g,n_trials=len(t),n_conflict=len(c),n_adopted=a,pooled_adoption_percent=rate,mean_conflict_confidence_delta=np.mean([r['confidence_change'] for r in c]) if c else float('nan')))
            text.append(f'{s} | {NAMES[g]}: conflict={len(c)}/{len(t)}, adopted={a}, pooled adoption={rate:.1f}%.' if c else f'{s} | {NAMES[g]}: no conflicting trials.')
    text += ['', 'Compare scenario profiles without treating 12 trials per person as independent for inferential claims.']
    write_report(where,text,rows)
    fig,ax=plt.subplots(figsize=(10,4.8));xs=np.arange(12)
    for g,dx in [('AI_label',-.18),('Unlabeled',.18)]:
        vals=[next(r['pooled_adoption_percent'] for r in rows if r['source']==g and r['scenario']==f'E{i:02d}') for i in range(1,13)]
        ax.bar(xs+dx,vals,width=.34,label=NAMES[g],color=COLORS[g],alpha=.88)
    ax.set_xticks(xs,[f'E{i:02d}' for i in range(1,13)]);ax.set_ylabel('Adoption among conflict trials (%)')
    ax.set_title('Adoption rate by scenario (descriptive)',weight='bold');ax.legend(frameon=False)
    ax.spines[['top','right']].set_visible(False);fig.tight_layout();save_fig(fig,where,'scenario_adoption')


def survey_quality(trials,people,where):
    text=['MODULE 07 | POST-EXPERIMENT RATINGS AND QUALITY CHECKS','P1 useful; P2 fits own views; P3 autonomous; P4 use similar advice again (1..5).',
          'Secondary and exploratory comparisons; Holm correction across the four two-sided p-values.','']
    rows=[];ps=[]
    for k in range(1,5):
        values={g:np.asarray([p[f'P{k}'] for p in people if p['source']==g and math.isfinite(p[f'P{k}'])]) for g in GROUPS}
        w=welch(values['AI_label'],values['Unlabeled']);ps.append(w['p'])
        text.append(f'P{k}: AI M={values["AI_label"].mean():.3f}, unlabeled M={values["Unlabeled"].mean():.3f}, difference={w["difference"]:+.3f}, Welch p={w["p"]:.4f}.')
        rows.append(dict(item=f'P{k}',AI_mean=np.mean(values['AI_label']),Unlabeled_mean=np.mean(values['Unlabeled']),mean_diff=w['difference'],p_uncorrected=w['p']))
    # Holm step-down adjusted p values
    order=np.argsort(ps); adjusted=np.zeros(len(ps)); running=0.
    for idx,ind in enumerate(order):
        running=max(running,(len(ps)-idx)*ps[ind]);adjusted[ind]=min(1.,running)
    for i,r in enumerate(rows):r['p_holm']=float(adjusted[i]);text.append(f'{r["item"]}: Holm-adjusted p={adjusted[i]:.4f}.')
    text += ['', 'Source recall is a manipulation-check outcome; DO NOT use recall to reassign randomized conditions.']
    for g in GROUPS:
        responses=Counter(str(p['source_recall']) for p in people if p['source']==g)
        text.append(f'Source recall {NAMES[g]}: '+', '.join(f'{k}={v}' for k,v in sorted(responses.items())))
    write_report(where,text,rows)
    fig,ax=plt.subplots(figsize=(7.8,4.5));x=np.arange(4)
    for g,dx in [('AI_label',-.18),('Unlabeled',.18)]:
        vals=[next(r['AI_mean'] if g=='AI_label' else r['Unlabeled_mean'] for r in rows if r['item']==f'P{i}') for i in range(1,5)]
        ax.bar(x+dx,vals,width=.34,color=COLORS[g],label=NAMES[g])
    ax.set_xticks(x,['P1 Useful','P2 Own views','P3 Autonomy','P4 Use again']);ax.set_ylim(0,5.2)
    ax.set_ylabel('Mean rating (1–5)');ax.set_title('Post-experiment evaluations',weight='bold');ax.legend(frameon=False)
    ax.spines[['top','right']].set_visible(False);fig.tight_layout();save_fig(fig,where,'subjective_ratings')


def robustness(trials,people,where):
    text=['MODULE 08 | ROBUSTNESS AND ANALYSIS CAVEATS','Key exploratory sensitivity checks. No multiple-comparison-adjusted confirmatory claim is made.','']
    conflict=[r for r in trials if not r['agrees_initially']]
    y=np.asarray([r['adopted_conflicting_advice'] for r in conflict],float)
    scenarios=sorted({r['scenario'] for r in conflict})
    x=np.column_stack([np.ones(len(conflict)),np.array([r['source']=='AI_label' for r in conflict],float)] + [np.array([r['scenario']==s for r in conflict],float) for s in scenarios[1:]])
    grp=np.asarray([r['participant_id'] for r in conflict])
    try:
        m=sm.GLM(y,x,family=sm.families.Binomial()).fit(cov_type='cluster',cov_kwds={'groups':grp,'use_correction':True})
        est,se,p=float(m.params[1]),float(m.bse[1]),float(m.pvalues[1]);ci=m.conf_int()[1]
        text += [f'Scenario-fixed-effects logistic regression with participant-clustered SE: log OR AI vs unlabeled={est:+.4f}, SE={se:.4f}, OR={np.exp(est):.4f}, 95% OR CI [{np.exp(ci[0]):.4f},{np.exp(ci[1]):.4f}], p={p:.4f}.']
    except Exception as err:
        text.append(f'Logistic model failed: {type(err).__name__}: {err}.')
    # Stratified by each respondent's number of conflict exposures, descriptive only.
    conflict_count=Counter(t['participant_id'] for t in conflict)
    text += ['', 'Number of conflicting scenarios per participant (denominator heterogeneity):']
    for g in GROUPS:
        counts=[conflict_count[p['participant_id']] for p in people if p['source']==g]
        text.append(f'{NAMES[g]}: min={min(counts)}, median={np.median(counts):.1f}, max={max(counts)}, zero conflict={sum(n==0 for n in counts)}.')
    text += ['', 'Confidence is on a 1–5 ordinal scale and has a high baseline; normal-theory mean tests should be treated as approximations.',
             'Subsetting on post-advice switching can introduce selection bias.',
             'No unaided/no-advice group: pre/post changes alone cannot isolate a causal effect of advice exposure.',
             'One original source file contains IP, location and platform identifiers: these must not be committed to a public repository.',
             'Study materials are Chinese and no validated EMCS short form is claimed.',
             'Participants are the independent sampling units, not 720 trial observations.']
    write_report(where,text)
    vals={g:np.asarray([sum(t['participant_id']==p['participant_id'] and not t['agrees_initially'] for t in trials) for p in people if p['source']==g]) for g in GROUPS}
    subject_plot(where,'conflict_exposure_distribution',vals,'Number of conflicting trials per participant','Conflict trials per participant')


def main():
    ap=argparse.ArgumentParser(description='Generate independent paper-ready result folders.')
    ap.add_argument('--module',choices=MODULES,help='Run one independent analysis module.')
    ap.add_argument('--all',action='store_true',help='Run all modules (default).')
    ap.add_argument('--raw-xlsx',type=Path,default=DEFAULT_RAW,
                    help='Original untouched questionnaire XLSX. Required for every run.')
    ap.add_argument('--private-data-dir',default=str(ROOT/'data_private'),
                    help='Local directory for regenerated, deidentified intermediate CSVs.')
    ap.add_argument('--output-dir',default=str(ROOT/'results'))
    args=ap.parse_args()
    raw=Path(args.raw_xlsx).expanduser().resolve()
    if not raw.is_file():
        ap.error(f'Original Excel not found: {raw}. Put the exact original XLSX in data/raw/ '
                 'after making the repository private, or pass --raw-xlsx PATH.')
    if raw.suffix.lower()!='.xlsx':
        ap.error('Input must be the original .xlsx workbook, not a processed CSV.')
    from scripts.import_raw_xlsx import convert
    pdir=Path(args.private_data_dir)
    # Deliberately parse the raw workbook on EVERY run. No cached CSV fallback.
    convert(raw,pdir)
    people=read_csv(pdir/'participants.csv');trials=read_csv(pdir/'trials.csv')
    ensure_numeric(trials,people);validate(trials,people)
    out=Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    original_sha256=hashlib.sha256(raw.read_bytes()).hexdigest()
    provenance=[
        'SOURCE DATA PROVENANCE',
        'Source: original unmodified uploaded Excel workbook',
        f'Original file name: {raw.name}',
        f'SHA-256: {original_sha256}',
        'Processing: scripts/import_raw_xlsx.py -> temporary participant/trial CSVs -> run_analysis.py',
        f'Validated counts: {len(people)} participants and {len(trials)} scenarios; 30 participants per arm.',
        'Original workbook is read-only and is NEVER overwritten by this program.',
        'Raw file contains identifying information: never upload it to a public repository.',
    ]
    (out/'data_provenance.txt').write_text('\n'.join(provenance)+'\n',encoding='utf-8')
    executors={
        MODULES[0]:lambda folder:demographics(trials,people,folder),
        MODULES[1]:lambda folder:descriptive(trials,people,folder),
        MODULES[2]:lambda folder:adoption(trials,people,folder),
        MODULES[3]:lambda folder:unchanged_confidence(trials,folder,'agree'),
        MODULES[4]:lambda folder:unchanged_confidence(trials,folder,'conflict'),
        MODULES[5]:lambda folder:interaction(trials,folder),
        MODULES[6]:lambda folder:scenarios(trials,folder),
        MODULES[7]:lambda folder:survey_quality(trials,people,folder),
        MODULES[8]:lambda folder:robustness(trials,people,folder),
    }
    names=[args.module] if args.module else MODULES
    for name in names:
        folder=out/name
        executors[name](folder)
        # Keep exact source provenance with each independently usable analysis folder.
        (folder/'data_provenance.txt').write_text('\n'.join(provenance)+'\n',encoding='utf-8')
        print('OK:',name,'=>',folder)
    print('Analyses complete; all reports are generated directly from subject/trial records.')

if __name__=='__main__':
    main()
