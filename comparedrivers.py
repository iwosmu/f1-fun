import streamlit as st
import fastf1
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

st.set_page_config(page_title='F1 Teammate Comparison', layout='wide')
st.title("F1 Teammate Performance Analyzer")

@st.cache_data
def load_schedule(year):
    schedule = fastf1.get_event_schedule(year)
    return schedule[schedule['EventFormat'] != 'testing']

@st.cache_data
def get_team_drivers(year, team_name):
    session = fastf1.get_session(year, 1, 'Q')
    session.load(telemetry = False, weather=False, messages=False)
    drivers = session.results[session.results['TeamName'] == team_name]['Abbreviation'].unique() #co kurwa
    return list(drivers)

st.sidebar.header('Settings')
year = st.sidebar.selectbox('Select Year', range(2025, 2017, -1), index = 0)

try:
    r1 = fastf1.get_session(year, 1, 'R')
    r1.load(telemetry=False, weather=False, messages=False)
    unique_teams = sorted(r1.results['TeamName'].unique())

    selected_team = st.sidebar.selectbox('Select Team', unique_teams)

    team_drivers = r1.results[r1.results['TeamName'] == selected_team]['Abbreviation'].tolist()

    if(len(team_drivers)) < 2:
        st.error('Not enough data to ifnd teammates for this team')
        st.stop()
    d1, d2 = team_drivers[0], team_drivers[1]
    st.sidebar.write(f"Analyzing: **{d1} vs {d2}**")

except Exception as e:
    st.error(f"Could not load team data for {year}. Fastf1 data might not be complete for this year yet")
    st.stop()

if st.sidebar.button('Run Season Analysis'):
    st.write(f"Analyzing {year} Season: {selected_team}")
    progress_bar = st.progress(0)

    schedule = load_schedule(year)
    results_data = []

    races_to_analyze = schedule['RoundNumber'].tolist()
    sprint_rounds = schedule[schedule['EventFormat'].isin(['sprint', 'sprint_qualifying', 'sprint_shootout'])]['RoundNumber'].tolist()

    total_races = len(races_to_analyze)

    for i, round_num in enumerate(races_to_analyze):
        try:
            session = fastf1.get_session(year, round_num, 'R')
            session.load(telemetry=False, weather=False, messages=False)

            race_res = session.results

            d1_row = race_res[race_res['Abbreviation']==d1]
            d2_row = race_res[race_res['Abbreviation']==d2]

            d1_pts = 0
            d2_pts = 0
            d1_pos = None
            d2_pos = None
            if not d1_row.empty:
                d1_pts = d1_row.iloc[0]['Points']
                d1_pos = d1_row.iloc[0]['Position']
            if not d2_row.empty:
                d2_pts = d2_row.iloc[0]['Points']
                d2_pos = d2_row.iloc[0]['Position']

            if round_num in sprint_rounds:
                try:
                    sprint = fastf1.get_session(year, round_num, 'Sprint')
                    sprint.load(telemetry=False, weather=False, messages=False)
                    sp_d1 = sprint.results[sprint.results['Abbreviation']==d1]
                    sp_d2 = sprint.results[sprint.results['Abbreviation']==d2]
                    if not sp_d1.empty: d1_pts += sp_d1.iloc[0]['Points']
                    if not sp_d2.empty: d2_pts += sp_d2.iloc[0]['Points']
                except Exception as e:
                    st.warning(f"Could not load spring data for Round {round_num}")


            if d1_pos is None and d2_pos is None:
                winner = "None"
            elif d2_pos is None:
                winner = d1
            elif d1_pos is None:
                winner = d2
            elif d1_pos < d2_pos:
                winner = d1
            else:
                winner = d2
            
            pace_diff = np.nan
            if d1_pos is not None and d2_pos is not None:
                laps = session.laps
                d1_laps = laps.pick_drivers(d1).pick_quicklaps().pick_accurate()
                d2_laps = laps.pick_drivers(d2).pick_quicklaps().pick_accurate()

                if not d1_laps.empty and not d2_laps.empty:
                    d1_pace = d1_laps['LapTime'].dt.total_seconds().median()
                    d2_pace = d2_laps['LapTime'].dt.total_seconds().median()
                    pace_diff = d1_pace - d2_pace
            
            results_data.append({
                'Round': round_num,
                'Race': session.event['EventName'],
                f'{d1}_pos': d1_pos,
                f'{d2}_Pos': d2_pos,
                f'{d1}_Pts': d1_pts,
                f'{d2}_Pts': d2_pts,
                'Ahead': winner,
                'Pace_Gap': pace_diff
            })
        except Exception as e:
            st.warning(f'Skipping Round {round_num}: {e}')
        
        progress_bar.progress((i+1) / total_races)
    df = pd.DataFrame(results_data)

    c1, c2, c3 = st.columns(3)
    d1_wins = len(df[df['Ahead']==d1])
    d2_wins = len(df[df['Ahead']==d2])

    c1.metric('Race Head-to-Head', f'{d1} {d1_wins} - {d2_wins} {d2}')
    c2.metric('Total Points', f'{d1} {df[f'{d1}_Pts'].sum()} - {df[f'{d2}_Pts'].sum()} {d2}')

    avg_gap = df['Pace_Gap'].mean()
    faster_driver = d1 if avg_gap < 0 else d2
    c3.metric('Avg Race Pace Gap', f'{faster_driver} is {abs(avg_gap):.3f}s faster/lap')

    st.subheader('Race Pace Gap per Race (seconds)')
    st.write(f"Positive values mean **{d2}** is faster, Negative mean **{d1}** is faster")

    fig = px.bar(df, x = 'Race', y='Pace_Gap',
                 title = f'Median Lap Time Delta ({d1} vs {d2})',
                 color = 'Pace_Gap',
                 color_continuous_scale=px.colors.diverging.RdBu)
    st.plotly_chart(fig, width='stretch')

    st.subheader('Championship Points Trajectory')
    df['Cum_Pts_D1'] = df[f'{d1}_Pts'].cumsum()
    df['Cum_Pts_D2'] = df[f'{d2}_Pts'].cumsum()

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df['Race'], y = df['Cum_Pts_D1'], mode = 'lines+markers', name=d1))
    fig2.add_trace(go.Scatter(x=df['Race'], y=df['Cum_Pts_D2'], mode='lines+markers', name = d2))
    st.plotly_chart(fig2, width='stretch')
else:
    st.info('Select a Year and Team, then click "Run Session Analysis"!')