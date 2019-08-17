import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import pandas as pd
import boto3

import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64

from IPython import display
import os
import io
import time
import json
import requests

def show_app(app, port = 9999,
             width = 700,
             height = 350,
             offline = False,
             in_binder = None):
    in_binder ='JUPYTERHUB_SERVICE_PREFIX' in os.environ if in_binder is None else in_binder
    if in_binder:
        base_prefix = '{}proxy/{}/'.format(os.environ['JUPYTERHUB_SERVICE_PREFIX'], port)
        url = 'https://hub.mybinder.org{}'.format(base_prefix)
        app.config.requests_pathname_prefix = base_prefix
    else:
        url = 'http://localhost:%d' % port

    iframe = '<a href="{url}" target="_new">Open in new window</a><hr><iframe src="{url}" width={width} height={height}></iframe>'.format(url = url,
                                                                                                                                          width = width,
                                                                                                                                          height = height)

    display.display_html(iframe, raw = True)
    if offline:
        app.css.config.serve_locally = True
        app.scripts.config.serve_locally = True
    return app.run_server(debug=False, # needs to be false in Jupyter
                          port=port)

def fig_to_uri(in_fig, close_all=True, **save_args):
    """
    Save a figure as a URI
    :param in_fig:
    :return:
    """
    out_img = BytesIO()
    in_fig.savefig(out_img, format='png', **save_args)
    if close_all:
        in_fig.clf()
        plt.close('all')
    out_img.seek(0)  # rewind file
    encoded = base64.b64encode(out_img.read()).decode("ascii").replace("\n", "")
    return "data:image/png;base64,{}".format(encoded)


dynamodb = boto3.resource('dynamodb',
                          # ,aws_session_token = aws_session_token,
                          aws_access_key_id = '',
                          aws_secret_access_key = '',
                          region_name = 'us-east-1'
                          )

bucket = "info7374s3alycefinalproject"
file_name = "gasoline.csv"

s3 = boto3.resource('s3',
                    # ,aws_session_token = aws_session_token,
                    aws_access_key_id = '',
                    aws_secret_access_key = '',
                    region_name = 'us-east-1'
                    )

s3 = boto3.client('s3')

obj = s3.get_object(Bucket= bucket, Key= file_name)

sales = pd.read_csv(obj['Body'])

sales['Total_revenue_lag1'] = sales['Total_revenue'].shift(1)
sales['Total_revenue_lag2'] = sales['Total_revenue'].shift(2)
sales['Total_revenue_lag3'] = sales['Total_revenue'].shift(3)
sales['Total_revenue_lag4'] = sales['Total_revenue'].shift(4)
sales['trend'] = np.arange(len(sales))
sales['log_trend'] = np.log1p(np.arange(len(sales)))
sales['sq_trend'] = np.arange(len(sales)) ** 2
weeks = pd.get_dummies(np.array(list(range(52)) * 15)[:len(sales)], prefix='week')
sales = pd.concat([sales, weeks], axis=1)

sales = sales.iloc[4:, ]
split_train = int(len(sales) * 0.6)
split_test = int(len(sales) * 0.8)

train_y = sales['Total_revenue'][:split_train]
train_X = sales.drop('Total_revenue', axis=1).iloc[:split_train, ].as_matrix()
validation_y = sales['Total_revenue'][split_train:split_test]
validation_X = sales.drop('Total_revenue', axis=1).iloc[split_train:split_test, ].as_matrix()
test_y = sales['Total_revenue'][split_test:]
test_X = sales.drop('Total_revenue', axis=1).iloc[split_test:, ].as_matrix()

def np2csv(arr):
    csv = io.BytesIO()
    np.savetxt(csv, arr, delimiter=',', fmt='%g')
    return csv.getvalue().decode().rstrip()

payload= np2csv(test_X)

r=requests.post("https://asfk7ybx5c.execute-api.us-east-1.amazonaws.com/final/sales", data =json.dumps(payload))

result = json.loads(r.content)

one_step = np.array([r['score'] for r in result['predictions']])

# Read Alyce Fact data
df_fact = dynamodb.Table('FinalAlyce_facts')
response = df_fact.scan()
df_fact = response['Items']

while 'LastEvaluatedKey' in response:
    response = df_fact.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
    df_fact.extend(response['Items'])

df_fact = pd.DataFrame(df_fact)

# Read Alyce Client data
df_client = dynamodb.Table('FinalAlyce_client')
response = df_client.scan()
df_client = response['Items']

while 'LastEvaluatedKey' in response:
    response = df_client.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
    df_client.extend(response['Items'])

df_client = pd.DataFrame(df_client)

# Read Alyce Gift data
df_gift = dynamodb.Table('FinalAlyce_giftdata')
response = df_gift.scan()
df_gift = response['Items']

while 'LastEvaluatedKey' in response:
    response = df_gift.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
    df_gift.extend(response['Items'])

df_gift = pd.DataFrame(df_gift)


df = pd.merge(df_fact, df_client, how='inner', left_on = 'client_id', right_on = 'client_id')

df = pd.merge(df, df_gift, how='inner', left_on = 'gift_id', right_on = 'gift_id')
df['date'] = pd.to_datetime(df['date'])
df['year'], df['month'] = df['date'].dt.year, df['date'].dt.month

client_name = df['client_name'].unique()
channel = df['client_acquisition_source'].unique()

# Boostrap CSS.
#app.css.append_css({'external_url': 'https://codepen.io/amyoshino/pen/jzXypZ.css'})  # noqa: E501

external_stylesheets = ['https://codepen.io/amyoshino/pen/jzXypZ.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

app.layout = html.Div(
    html.Div([
        html.Div(
            [
                html.H1(children='Alyce',
                        className='nine columns'),
                html.Div(children='''
                        A web application for Analytical purpose.
                        ''',
                         className='nine columns'
                         )
            ], className="row"
        ),
        dcc.Graph(id='graph-with-slider'),
        dcc.Slider(
            id='year-slider',
            min=df['year'].min(),
            max=df['year'].max(),
            value=df['year'].min(),
            marks={str(year): str(year) for year in df['year'].unique()},
            step=None
        ),
        html.Div([
            html.Div([dcc.Dropdown(id='channel-selected1',
                                   options=[{
                                       'label': i,
                                       'value': i
                                   } for i in channel],
                                   value='email')], className="six columns",
                     style={"width": "40%", "float": "right"}),
            html.Div([dcc.Dropdown(id='Clients1',
                                   options=[{
                                       'label': i,
                                       'value': i
                                   } for i in client_name],
                                   value='All')], className="six columns", style={"width": "40%", "float": "left"}),
        ], className="row", style={"padding": 50, "width": "60%", "margin-left": "auto", "margin-right": "auto"}),
        dcc.Graph(id='my-graph'),
        dcc.Input(id='plot_title', value='Type title...', type="text"),
        # dcc.Slider(
        #     id='box_size',
        #     min=1,
        #     max=10,
        #     value=4,
        #     step=1,
        # ),
            html.Div([html.Img(id = 'cur_plot', src = '')],
                 id='plot_div'),
    ], className='ten columns offset-by-one')
)

@app.callback(
    dash.dependencies.Output('graph-with-slider', 'figure'),
    [dash.dependencies.Input('year-slider', 'value')])
def update_figure(selected_year):
    filtered_df = df[df.year == selected_year]
    traces = []
    for i in filtered_df.gift_name.unique():
        df_by_gift_name = filtered_df[filtered_df['gift_name'] == i]
        traces.append(go.Scatter(
            x=df_by_gift_name['total_revenue'],
            y=df_by_gift_name['total_gifts'],
            #text=df_by_gift_name['client_subscription'],
            mode='markers',
            opacity=0.7,
            # marker={
            #     'size': 15,
            #     'line': {'width': 0.5, 'color': 'white'}
            # },
            name=i
        ))

    return {
        'data': traces,
        'layout': go.Layout(
            xaxis={'type': 'log', 'title': 'Gift Cost'},
            yaxis={'title': 'Total Gifts', 'range': [20, 90]},
            margin={'l': 40, 'b': 40, 't': 10, 'r': 10},
            legend={'x': 0, 'y': 1},
            hovermode='closest'
        )
    }


@app.callback(
    dash.dependencies.Output('my-graph', 'figure'),
    [dash.dependencies.Input('Clients1', 'value'),
     dash.dependencies.Input('channel-selected1','value')])
def update_graph(selected_client, selected_channel):
    if selected_client == "All":
        df_plot = df.copy()
    else:
        df_plot = df[(df['client_name'] == selected_client) & (df['client_acquisition_source'] == selected_channel)]

    #dff = df[selected_client]
    #dff = df[df[selected_sub]]
    trace1 = go.Bar(x=df_plot['client_statecode'], y=df_plot['total_amount'], name="Total Amount" )
    trace2 = go.Bar(x=df_plot['client_statecode'], y=df_plot['total_revenue'], name="Total Revenue" )

    return {
        'data': [trace1,trace2],
        'layout': go.Layout(title='Total Revenue by client',
                            colorway=["#EF963B", "#EF533B"], hovermode="closest",
                            xaxis={'title': "State", 'titlefont': {'color': 'black', 'size': 14},
                                   'tickfont': {'size': 9, 'color': 'black'}}
                            # yaxis={'title': "Export price (million USD)", 'titlefont': {'color': 'black', 'size': 14, },
                            #        'tickfont': {'color': 'black'}}
                            )}

@app.callback(
dash.dependencies.Output(component_id='cur_plot', component_property='src'),
[dash.dependencies.Input(component_id='plot_title', component_property='value')])#,dash.dependencies.Input(component_id = 'box_size', component_property='value')])
def update_graph(input_value):
    # fig, ax1 = plt.subplots(1,1)
    # np.random.seed(len(input_value))
    # ax1.matshow(np.random.uniform(-1,1))
    # ax1.set_title(input_value)
    # out_url = fig_to_uri(fig)
    # return out_url

    plt.plot(np.array(test_y), label='actual')
    plt.plot(one_step, label='forecast')
    plt.legend()
    plt.show()

show_app(app)

# if __name__ == '__main__':
#     app.run_server(debug=True)