import pandas as pd
import numpy as np
from typing import IO
from typing import Dict, List, Any

# Constants
MAX_CATEGORICAL_COLUMNS = 5
TOP_CATEGORICAL_VALUES_COUNT = 10
CORRELATION_THRESHOLD = 0.5

class DataProcessor:
    """Efficient data processing using Pandas"""

    def load_data(self, source: Any, file_extension: str | None = None) -> pd.DataFrame:
        """Load data from various file formats"""
        if file_extension is None:
            if not isinstance(source, str):
                raise ValueError("file_extension is required for non-path sources")
            file_extension = source.rsplit('.', 1)[1].lower()

        if file_extension not in ['csv', 'xlsx', 'xls', 'json']:
            raise ValueError(f"Unsupported file format: {file_extension}")

        # Load based on file type with proper error handling
        try:
            if file_extension == 'csv':
                df = pd.read_csv(source)
            elif file_extension in ['xlsx', 'xls']:
                df = pd.read_excel(source)
            elif file_extension == 'json':
                # Try multiple JSON formats
                try:
                    # First try records format (most common)
                    df = pd.read_json(source, orient='records')
                except ValueError:
                    try:
                        # Try default format
                        df = pd.read_json(source)
                    except ValueError:
                        # Try table format
                        df = pd.read_json(source, orient='table')
            
            # Optimization: Downcast numerics
            for col in df.select_dtypes(include=['integer']).columns:
                df[col] = pd.to_numeric(df[col], downcast='integer')

            for col in df.select_dtypes(include=['floating']).columns:
                df[col] = pd.to_numeric(df[col], downcast='float')
                    
            # Optimization: Convert low cardinality objects to category
            for col in df.select_dtypes(include=['object', 'string']).columns:
                num_unique = df[col].nunique()
                num_total = len(df[col])
                if num_total > 0 and num_unique / num_total < 0.5:
                    df[col] = df[col].astype('category')
                    
            return df
        except Exception as e:
            raise ValueError(f"Failed to load {file_extension} file: {str(e)}")
    
    def get_columns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Get column information with data types"""
        return [{
            'name': col,
            'dtype': str(df[col].dtype),
            'is_numeric': pd.api.types.is_numeric_dtype(df[col]),
            'is_datetime': pd.api.types.is_datetime64_any_dtype(df[col]),
            'null_count': int(df[col].isnull().sum()),
            'unique_count': int(df[col].nunique())
        } for col in df.columns]
    
    def get_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get basic summary statistics"""
        summary = {
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'missing_values': {k: int(v) for k, v in df.isnull().sum().items()},
            'memory_usage': int(df.memory_usage(deep=True).sum())
        }
        
        # Add numeric summary if numeric columns exist
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            desc = df[numeric_cols].describe()
            summary['numeric_summary'] = {
                col: {k: float(v) if not pd.isna(v) else None for k, v in desc[col].items()}
                for col in numeric_cols
            }
        
        return summary
    
    def get_detailed_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Perform detailed statistical analysis"""
        analysis = {'basic_stats': {}, 'correlations': {}, 'categorical_analysis': {}}
        
        # Numeric statistics
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            desc = df[numeric_cols].describe()
            analysis['basic_stats'] = {
                col: {
                    stat: float(desc[col][stat]) if not pd.isna(desc[col][stat]) else None
                    for stat in ['mean', 'std', 'min', '25%', '50%', '75%', 'max']
                } for col in numeric_cols
            }
            
            # Add median explicitly
            for col in numeric_cols:
                analysis['basic_stats'][col]['median'] = float(df[col].median(skipna=True)) if not pd.isna(df[col].median(skipna=True)) else None
                analysis['basic_stats'][col]['q25'] = analysis['basic_stats'][col].pop('25%')
                analysis['basic_stats'][col]['q75'] = analysis['basic_stats'][col].pop('75%')
            
            # Correlation matrix
            if len(numeric_cols) > 1:
                corr_matrix = df[numeric_cols].corr()
                analysis['correlations'] = {
                    'matrix': {
                        str(col): {str(k): float(v) if not pd.isna(v) else None for k, v in corr_matrix[col].items()}
                        for col in corr_matrix.columns
                    },
                    'pairs': self._get_correlation_pairs(corr_matrix)
                }
        
        # Categorical analysis
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        if categorical_cols:
            for col in categorical_cols[:MAX_CATEGORICAL_COLUMNS]:
                if df[col].notnull().sum() > 0:
                    value_counts = df[col].value_counts(dropna=True).head(TOP_CATEGORICAL_VALUES_COUNT)
                    mode = df[col].mode(dropna=True)
                    analysis['categorical_analysis'][col] = {
                        'unique_values': int(df[col].nunique()),
                        'top_values': {str(k): int(v) for k, v in value_counts.items()},
                        'mode': str(mode[0]) if not mode.empty else None
                    }
                else:
                    analysis['categorical_analysis'][col] = {
                        'unique_values': 0,
                        'top_values': {},
                        'mode': None
                    }

        return analysis

    def _get_correlation_pairs(self, corr_matrix: pd.DataFrame, threshold: float = CORRELATION_THRESHOLD) -> List[Dict]:
        """Get strongly correlated pairs"""
        pairs = []
        n = len(corr_matrix.columns)
        for i in range(n):
            for j in range(i + 1, n):
                corr_value = corr_matrix.iloc[i, j]
                if not pd.isna(corr_value) and abs(corr_value) > threshold:
                    pairs.append({
                        'var1': str(corr_matrix.columns[i]),
                        'var2': str(corr_matrix.columns[j]),
                        'correlation': float(corr_value)
                    })
        return sorted(pairs, key=lambda x: abs(x['correlation']), reverse=True)
