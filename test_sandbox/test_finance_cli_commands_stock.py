import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from finance_cli.commands.stock import (
    stock,
    get_quote,
    get_history,
    get_financials,
    get_news,
    get_recommendations,
    get_earnings,
    get_dividends,
    get_splits,
    get_options
)


class TestStockCommands:
    """测试股票相关命令"""
    
    def setup_method(self):
        """测试前准备"""
        self.runner = CliRunner()
        
    def test_stock_group_exists(self):
        """测试 stock 命令组存在"""
        result = self.runner.invoke(stock, ['--help'])
        assert result.exit_code == 0
        assert '股票数据查询命令' in result.output
        
    def test_get_quote_basic(self):
        """测试获取股票报价基本功能"""
        # 模拟 yfinance 的 Ticker 对象
        mock_ticker = Mock()
        mock_ticker.info = {
            'symbol': 'AAPL',
            'currentPrice': 175.25,
            'previousClose': 172.50,
            'volume': 50000000
        }
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_quote, ['AAPL'])
            
            assert result.exit_code == 0
            assert 'AAPL' in result.output
            assert '175.25' in result.output
            
    def test_get_quote_with_details(self):
        """测试获取股票报价带详细信息"""
        mock_ticker = Mock()
        mock_ticker.info = {
            'symbol': 'GOOGL',
            'currentPrice': 135.75,
            'marketCap': 1700000000000,
            'dayHigh': 136.50,
            'dayLow': 134.80
        }
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_quote, ['GOOGL', '--details'])
            
            assert result.exit_code == 0
            assert 'GOOGL' in result.output
            assert 'marketCap' in result.output.lower()
            
    def test_get_history_basic(self):
        """测试获取历史价格数据"""
        mock_ticker = Mock()
        # 模拟历史数据 DataFrame
        mock_history = Mock()
        mock_history.empty = False
        mock_history.shape = (100, 6)
        mock_ticker.history.return_value = mock_history
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_history, ['MSFT', '--period', '1mo'])
            
            assert result.exit_code == 0
            assert '历史价格数据' in result.output
            
    def test_get_history_with_interval(self):
        """测试获取不同时间间隔的历史数据"""
        mock_ticker = Mock()
        mock_history = Mock()
        mock_history.empty = False
        mock_ticker.history.return_value = mock_history
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_history, 
                                       ['TSLA', '--period', '1d', '--interval', '5m'])
            
            assert result.exit_code == 0
            mock_ticker.history.assert_called_with(period='1d', interval='5m')
            
    def test_get_financials(self):
        """测试获取财务报表数据"""
        mock_ticker = Mock()
        # 模拟财务报表数据
        mock_financials = {
            'income_stmt': Mock(),
            'balance_sheet': Mock(),
            'cash_flow': Mock()
        }
        mock_ticker.financials = mock_financials['income_stmt']
        mock_ticker.balance_sheet = mock_financials['balance_sheet']
        mock_ticker.cashflow = mock_financials['cash_flow']
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_financials, ['AMZN'])
            
            assert result.exit_code == 0
            assert '财务报表' in result.output
            
    def test_get_news(self):
        """测试获取新闻数据"""
        mock_ticker = Mock()
        mock_news = [
            {'title': 'Test News 1', 'publisher': 'Reuters', 'link': 'http://example.com'},
            {'title': 'Test News 2', 'publisher': 'Bloomberg', 'link': 'http://example2.com'}
        ]
        mock_ticker.news = mock_news
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_news, ['NVDA'])
            
            assert result.exit_code == 0
            assert 'Test News 1' in result.output
            assert 'Reuters' in result.output
            
    def test_get_recommendations(self):
        """测试获取分析师推荐"""
        mock_ticker = Mock()
        mock_recommendations = Mock()
        mock_recommendations.empty = False
        mock_ticker.recommendations = mock_recommendations
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_recommendations, ['JPM'])
            
            assert result.exit_code == 0
            assert '分析师推荐' in result.output
            
    def test_get_earnings(self):
        """测试获取盈利数据"""
        mock_ticker = Mock()
        mock_earnings = {
            'quarterly_earnings': Mock(),
            'quarterly_revenue': Mock()
        }
        mock_ticker.quarterly_earnings = mock_earnings['quarterly_earnings']
        mock_ticker.quarterly_revenue = mock_earnings['quarterly_revenue']
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_earnings, ['V'])
            
            assert result.exit_code == 0
            assert '盈利数据' in result.output
            
    def test_get_dividends(self):
        """测试获取股息数据"""
        mock_ticker = Mock()
        mock_dividends = Mock()
        mock_dividends.empty = False
        mock_ticker.dividends = mock_dividends
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_dividends, ['PG'])
            
            assert result.exit_code == 0
            assert '股息数据' in result.output
            
    def test_get_splits(self):
        """测试获取拆股数据"""
        mock_ticker = Mock()
        mock_splits = Mock()
        mock_splits.empty = False
        mock_ticker.splits = mock_splits
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_splits, ['HD'])
            
            assert result.exit_code == 0
            assert '拆股数据' in result.output
            
    def test_get_options(self):
        """测试获取期权数据"""
        mock_ticker = Mock()
        mock_options = Mock()
        mock_options.empty = False
        mock_ticker.options = ['2024-01-19', '2024-02-16']
        mock_ticker.option_chain.return_value = Mock()
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_options, ['SPY', '--expiry', '2024-01-19'])
            
            assert result.exit_code == 0
            assert '期权数据' in result.output
            
    def test_invalid_symbol(self):
        """测试无效股票代码"""
        mock_ticker = Mock()
        mock_ticker.info = {}
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_quote, ['INVALID'])
            
            # 根据实际实现，可能是非零退出码或特定错误信息
            assert result.exit_code != 0 or '错误' in result.output or '无效' in result.output
            
    def test_network_error_handling(self):
        """测试网络错误处理"""
        with patch('finance_cli.commands.stock.yf.Ticker', side_effect=Exception('Network error')):
            result = self.runner.invoke(get_quote, ['AAPL'])
            
            # 应该优雅地处理错误
            assert '错误' in result.output or 'Exception' in result.output
            
    def test_output_format_json(self):
        """测试 JSON 输出格式"""
        mock_ticker = Mock()
        mock_ticker.info = {'symbol': 'AAPL', 'currentPrice': 175.25}
        
        with patch('finance_cli.commands.stock.yf.Ticker', return_value=mock_ticker):
            result = self.runner.invoke(get_quote, ['AAPL', '--format', 'json'])
            
            assert result.exit_code == 0
            # 检查是否是有效的 JSON
            import json
            try:
                json.loads(result.output)
                assert True
            except json.JSONDecodeError:
                assert False, "输出不是有效的 JSON"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])