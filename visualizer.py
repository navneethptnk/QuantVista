import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from typing import Optional

MAX_ROWS_SCATTER = 50000
MAX_PIE_SLICES = 6
DEFAULT_HEIGHT = 650
AUTO_SCALE_SPREAD_THRESHOLD = 0.20


class Visualizer:

    def __init__(self):
        self.default_colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']
        self.highlight_color = "#FF6B6B"

    def create_chart(
        self,
        df: pd.DataFrame,
        chart_type: str,
        x: str,
        y: Optional[str] = None,
        z: Optional[str] = None,
        color: Optional[str] = None,
        agg: str = "sum",
        auto_scale: bool = True,
        title: str = "Data Visualization"
    ):

        self._validate_dataframe(df)
        self._validate_columns(df, x, y, z, color)

        chart_map = {
            "bar": self._bar,
            "line": self._line,
            "scatter": self._scatter,
            "pie": self._pie,
            "histogram": self._histogram,
            "box": self._box,
            "area": self._area,
            "bubble": self._bubble,
            "heatmap": self._heatmap,
            "violin": self._violin,
            "sunburst": self._sunburst,
            "treemap": self._treemap
        }

        if chart_type not in chart_map:
            raise ValueError(f"Unsupported chart type: {chart_type}")

        return chart_map[chart_type](df, x, y, z, color, agg, auto_scale, title)

    def _validate_dataframe(self, df):
        if df is None or df.empty:
            raise ValueError("DataFrame is empty")

    def _validate_columns(self, df, *cols):
        for col in cols:
            if col and pd.notna(col) and col not in df.columns:
                raise ValueError(f"Column '{col}' not found in dataset")

    def _require_numeric(self, df, col, chart):
        if not col:
            raise ValueError(f"{chart} requires a numeric column")
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in dataset")
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"{chart} requires numeric column '{col}'")

    def _can_add_trendline(self) -> bool:
        try:
            import statsmodels  # noqa: F401
            return True
        except Exception:
            return False

    def _aggregate(self, df, x, y=None, agg="sum"):
        if y and pd.api.types.is_numeric_dtype(df[y]):
            if agg == "count":
                return df.groupby(x, as_index=False).size().rename(columns={"size": y})
            if agg in {"sum", "mean", "median"}:
                return df.groupby(x, as_index=False)[y].agg(agg)
            return df.groupby(x, as_index=False)[y].sum()
        counts = df[x].value_counts().reset_index()
        counts.columns = [x, 'count']
        return counts

    def _apply_layout(self, fig, title, x_label=None, y_label=None, y_values=None, auto_scale=True):
        """Apply consistent professional styling"""
        fig.update_layout(
            title=dict(
                text=f'<b>{title}</b>',
                font=dict(size=24, family='Inter, Arial, sans-serif', color='#0f172a'),
                x=0.5,
                xanchor='center'
            ),
            plot_bgcolor='rgba(248, 250, 252, 0.5)',
            paper_bgcolor='white',
            font=dict(family='Inter, Arial, sans-serif', size=13),
            hovermode='closest',
            margin=dict(l=60, r=30, t=80, b=70),
            height=DEFAULT_HEIGHT
        )

        if x_label:
            fig.update_xaxes(
                title=dict(text=f'<b>{x_label}</b>', font=dict(size=15, color='#1e293b')),
                tickfont=dict(size=12, color='#475569'),
                gridcolor='rgba(148, 163, 184, 0.15)',
                automargin=True
            )

        if y_label:
            fig.update_yaxes(
                title=dict(text=f'<b>{y_label}</b>', font=dict(size=15, color='#1e293b')),
                tickfont=dict(size=12, color='#475569'),
                gridcolor='rgba(148, 163, 184, 0.15)',
                automargin=True
            )
            if auto_scale:
                self._apply_smart_yaxis_range(fig, y_values)

        return fig

    def _apply_smart_yaxis_range(self, fig, y_values):
        if y_values is None:
            return

        series = pd.to_numeric(pd.Series(y_values), errors='coerce').dropna()
        if series.empty:
            return

        min_val = float(series.min())
        max_val = float(series.max())

        # For near-identical values, zoom the axis around actual values so differences are visible.
        if np.isclose(min_val, max_val):
            base = max(abs(max_val), 1.0)
            pad = max(base * 0.02, 0.1 if base < 10 else 1.0)
            fig.update_yaxes(range=[min_val - pad, max_val + pad], rangemode='normal')
            return

        spread = max_val - min_val
        scale = max(abs(min_val), abs(max_val), 1.0)
        relative_spread = spread / scale

        if relative_spread < AUTO_SCALE_SPREAD_THRESHOLD:
            pad = max(spread * 0.20, scale * 0.01)
            fig.update_yaxes(range=[min_val - pad, max_val + pad], rangemode='normal')

    def _format_number(self, value):
        """Format numbers with K/M/B notation"""
        if pd.isna(value):
            return 'N/A'
        abs_value = abs(value)
        if abs_value >= 1_000_000_000:
            return f'{value/1_000_000_000:.2f}B'
        elif abs_value >= 1_000_000:
            return f'{value/1_000_000:.2f}M'
        elif abs_value >= 1_000:
            return f'{value/1_000:.2f}K'
        else:
            return f'{value:.2f}'

    # ==========================================================
    # BAR CHART
    # ==========================================================

    def _bar(self, df, x, y, z, color, agg, auto_scale, title):
        agg_df = self._aggregate(df, x, y, agg)
        value_col = agg_df.columns[1]
        agg_df = agg_df.sort_values(by=value_col, ascending=False)

        # Calculate metrics
        total_sum = agg_df[value_col].sum()
        agg_df['pct'] = (agg_df[value_col] / total_sum * 100).round(1)
        max_val = agg_df[value_col].max()
        agg_df['diff_from_top'] = ((agg_df[value_col] - max_val) / max_val * 100).round(1) if max_val != 0 else 0

        # Assign colors
        colors = [
            self.highlight_color if i == 0 else self.default_colors[i % len(self.default_colors)]
            for i in range(len(agg_df))
        ]

        fig = go.Figure(
            go.Bar(
                x=agg_df[x].tolist(),
                y=agg_df[value_col].tolist(),
                marker=dict(color=colors, line=dict(width=2, color='white')),
                text=[self._format_number(v) for v in agg_df[value_col]],
                textposition='outside',
                textfont=dict(size=14, family='Inter, Arial, sans-serif', color='#1e293b'),
                hovertemplate='<b>%{x}</b><br>' +
                             f'<b>{value_col}:</b> %{{y:,.0f}}<br>' +
                             '<b>% of Total:</b> %{customdata[0]:.1f}%<br>' +
                             '<b>Diff from Top:</b> %{customdata[1]:.1f}%<extra></extra>',
                customdata=np.column_stack((agg_df['pct'], agg_df['diff_from_top'])).tolist(),
                width=0.6
            )
        )

        fig = self._apply_layout(fig, title, x, value_col, agg_df[value_col], auto_scale)
        fig.update_xaxes(tickangle=0)
        fig.update_layout(bargap=0.15)

        # Add summary annotation
        min_val = agg_df[value_col].min()
        max_val_display = agg_df[value_col].max()

        summary = f"<b>Range:</b> {self._format_number(min_val)} to {self._format_number(max_val_display)} | <b>Total:</b> {self._format_number(total_sum)}"
        fig.add_annotation(
            text=summary,
            xref="paper", yref="paper",
            x=0.5, y=-0.15,
            showarrow=False,
            font=dict(size=11, family='Inter, Arial, sans-serif', color='#64748b'),
            xanchor='center',
            bgcolor='rgba(248, 250, 252, 0.8)',
            bordercolor='rgba(203, 213, 225, 0.5)',
            borderwidth=1,
            borderpad=6
        )

        return fig

    # ==========================================================
    # LINE CHART
    # ==========================================================

    def _line(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, y, "Line chart")

        if color and color in df.columns:
            fig = px.line(df, x=x, y=y, color=color, markers=True,
                         color_discrete_sequence=self.default_colors)
        else:
            fig = go.Figure(data=[
                go.Scatter(
                    x=df[x],
                    y=df[y],
                    mode='lines+markers',
                    line=dict(color=self.default_colors[0], width=3),
                    marker=dict(size=6, color=self.default_colors[0]),
                    hovertemplate='<b>%{x}</b><br>%{y:,.2f}<extra></extra>'
                )
            ])

        fig = self._apply_layout(fig, title, x, y, df[y], auto_scale)
        fig.update_layout(showlegend=bool(color))
        return fig

    # ==========================================================
    # SCATTER CHART
    # ==========================================================

    def _scatter(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, x, "Scatter")
        self._require_numeric(df, y, "Scatter")

        if len(df) > MAX_ROWS_SCATTER:
            df = df.sample(MAX_ROWS_SCATTER)

        if color and color in df.columns:
            scatter_kwargs = {
                "x": x,
                "y": y,
                "color": color,
                "color_discrete_sequence": self.default_colors,
            }
            if self._can_add_trendline():
                scatter_kwargs["trendline"] = "ols"
            fig = px.scatter(df, **scatter_kwargs)
        else:
            fig = go.Figure(data=[
                go.Scatter(
                    x=df[x],
                    y=df[y],
                    mode='markers',
                    marker=dict(size=8, color=self.default_colors[0], opacity=0.7,
                              line=dict(width=1, color='white')),
                    hovertemplate='<b>X:</b> %{x:,.2f}<br><b>Y:</b> %{y:,.2f}<extra></extra>'
                )
            ])

        # Add correlation
        corr = df[[x, y]].corr().iloc[0, 1]
        fig.add_annotation(
            text=f"<b>Correlation:</b> {corr:.3f}",
            xref="paper", yref="paper",
            x=0.95, y=0.95,
            showarrow=False,
            font=dict(size=13),
            bgcolor='rgba(255, 255, 255, 0.9)',
            bordercolor='rgba(203, 213, 225, 0.5)',
            borderwidth=1,
            borderpad=6
        )

        fig = self._apply_layout(fig, title, x, y, df[y], auto_scale)
        fig.update_layout(showlegend=bool(color))
        return fig

    # ==========================================================
    # PIE CHART
    # ==========================================================

    def _pie(self, df, x, y, z, color, agg, auto_scale, title):
        if not y:
            # Pie charts can just count the occurrences of X if Y isn't provided
            agg_df = df.groupby(x).size().reset_index(name='count')
            value_col = 'count'
            agg = "count"
        else:
            self._require_numeric(df, y, "Pie chart")
            agg_df = self._aggregate(df, x, y, agg)
            value_col = agg_df.columns[1]

        # Get column names from aggregated dataframe
        x_col = x  # Category column name stays the same

        # Sort by values descending
        agg_df = agg_df.sort_values(by=value_col, ascending=False)

        # Handle too many slices
        if len(agg_df) > MAX_PIE_SLICES:
            top = agg_df.head(MAX_PIE_SLICES)
            others_value = agg_df.iloc[MAX_PIE_SLICES:][value_col].sum()
            others = pd.DataFrame({x_col: ["Others"], value_col: [others_value]})
            agg_df = pd.concat([top, others], ignore_index=True)

        # Extract labels and values
        labels = agg_df[x_col].tolist()
        values = agg_df[value_col].tolist()

        fig = go.Figure(data=[
            go.Pie(
                labels=labels,
                values=values,
                marker=dict(colors=self.default_colors, line=dict(color='white', width=2)),
                textinfo='label+percent',
                textfont=dict(size=13),
                hovertemplate='<b>%{label}</b><br>Value: %{value:,.0f}<br>Percentage: %{percent}<extra></extra>',
                hole=0.3
            )
        ])

        fig = self._apply_layout(fig, title, auto_scale=auto_scale)
        fig.update_layout(showlegend=True)
        return fig

    # ==========================================================
    # HISTOGRAM
    # ==========================================================

    def _histogram(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, x, "Histogram")

        fig = px.histogram(df, x=x, color=color, nbins=30,
                          color_discrete_sequence=self.default_colors)
        fig.update_traces(marker=dict(line=dict(width=1, color='white')))
        fig = self._apply_layout(fig, title, x, 'Frequency', auto_scale=auto_scale)
        fig.update_layout(showlegend=bool(color), bargap=0.1)
        return fig

    # ==========================================================
    # BOX
    # ==========================================================

    def _box(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, y, "Box plot")

        fig = px.box(df, x=x, y=y, color=color,
                    color_discrete_sequence=self.default_colors)
        fig = self._apply_layout(fig, title, x, y, df[y], auto_scale)
        fig.update_layout(showlegend=bool(color))
        return fig

    # ==========================================================
    # AREA
    # ==========================================================

    def _area(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, y, "Area chart")

        if color and color in df.columns:
            fig = px.area(df, x=x, y=y, color=color,
                         color_discrete_sequence=self.default_colors)
        else:
            # Parse color for fill
            try:
                if self.default_colors[0].startswith('#') and len(self.default_colors[0]) == 7:
                    r = int(self.default_colors[0][1:3], 16)
                    g = int(self.default_colors[0][3:5], 16)
                    b = int(self.default_colors[0][5:7], 16)
                    fillcolor = f'rgba({r}, {g}, {b}, 0.3)'
                else:
                    fillcolor = 'rgba(99, 110, 250, 0.3)'
            except (ValueError, IndexError):
                fillcolor = 'rgba(99, 110, 250, 0.3)'

            fig = go.Figure(data=[
                go.Scatter(
                    x=df[x],
                    y=df[y],
                    fill='tozeroy',
                    mode='lines',
                    line=dict(color=self.default_colors[0], width=2),
                    fillcolor=fillcolor
                )
            ])

        fig = self._apply_layout(fig, title, x, y, df[y], auto_scale)
        fig.update_layout(showlegend=bool(color))
        return fig

    # ==========================================================
    # BUBBLE
    # ==========================================================

    def _bubble(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, x, "Bubble")
        self._require_numeric(df, y, "Bubble")
        self._require_numeric(df, z, "Bubble")

        fig = px.scatter(df, x=x, y=y, size=z, color=color, size_max=60,
                        color_discrete_sequence=self.default_colors)
        fig = self._apply_layout(fig, title, x, y, df[y], auto_scale)
        fig.update_layout(showlegend=bool(color))
        return fig

    # ==========================================================
    # HEATMAP
    # ==========================================================

    def _heatmap(self, df, x, y, z, color, agg, auto_scale, title):
        if not z:
            numeric_df = df.select_dtypes(include=np.number)
            if numeric_df.shape[1] < 2:
                raise ValueError("Heatmap requires at least two numeric columns for correlation mode")
            corr = numeric_df.corr()
            fig = go.Figure(
                go.Heatmap(
                    z=corr.values,
                    x=corr.columns,
                    y=corr.columns,
                    colorscale="Blues",
                    hovertemplate='<b>%{x} vs %{y}</b><br>Correlation: %{z:.3f}<extra></extra>',
                    colorbar=dict(title='Correlation')
                )
            )
        else:
            if not x or not y:
                raise ValueError("Heatmap requires X and Y columns when Z is provided")
            self._require_numeric(df, z, "Heatmap values (Z)")
            pivot = df.pivot_table(index=y, columns=x, values=z, aggfunc="sum", fill_value=0)
            fig = go.Figure(
                go.Heatmap(
                    z=pivot.values,
                    x=pivot.columns,
                    y=pivot.index,
                    colorscale="Blues",
                    hovertemplate='<b>X:</b> %{x}<br><b>Y:</b> %{y}<br><b>Value:</b> %{z:,.0f}<extra></extra>',
                    colorbar=dict(title='Value')
                )
            )

        fig = self._apply_layout(fig, title, x, y, auto_scale=auto_scale)
        return fig

    # ==========================================================
    # VIOLIN
    # ==========================================================

    def _violin(self, df, x, y, z, color, agg, auto_scale, title):
        self._require_numeric(df, y, "Violin plot")

        fig = px.violin(df, x=x, y=y, color=color, box=True,
                       color_discrete_sequence=self.default_colors)
        fig = self._apply_layout(fig, title, x, y, df[y], auto_scale)
        fig.update_layout(showlegend=bool(color))
        return fig

    # ==========================================================
    # SUNBURST
    # ==========================================================

    def _sunburst(self, df, x, y, z, color, agg, auto_scale, title):
        agg_df = self._aggregate(df, x, y, agg)
        value_col = agg_df.columns[1]

        fig = px.sunburst(agg_df, path=[x], values=value_col,
                         color_discrete_sequence=self.default_colors)
        fig = self._apply_layout(fig, title, auto_scale=auto_scale)
        fig.update_traces(textinfo='label+percent parent')
        return fig

    # ==========================================================
    # TREEMAP
    # ==========================================================

    def _treemap(self, df, x, y, z, color, agg, auto_scale, title):
        agg_df = self._aggregate(df, x, y, agg)
        value_col = agg_df.columns[1]

        fig = px.treemap(agg_df, path=[x], values=value_col,
                        color_discrete_sequence=self.default_colors)
        fig = self._apply_layout(fig, title, auto_scale=auto_scale)
        fig.update_traces(
            textinfo='label+value+percent parent',
            marker=dict(line=dict(width=2, color='white'))
        )
        return fig
