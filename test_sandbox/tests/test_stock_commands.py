import pytest
from unittest.mock import patch, MagicMock
from finance_cli.commands.stock import get_stock_price, format_stock_price


class TestFormatStockPrice:
    """测试 format_stock_price 函数"""
    
    def test_format_usd(self):
        """测试美元格式化"""
        result = format_stock_price(123.456, "USD")
        assert result == "$123.46"
    
    def test_format_cny(self):
        """测试人民币格式化"""
        result = format_stock_price(123.456, "CNY")
        assert result == "¥123.46"
    
    def test_format_zero(self):
        """测试零值格式化"""
        result = format_stock_price(0, "USD")
        assert result == "$0.00"
    
    def test_format_negative(self):
        """测试负值格式化"""
        result = format_stock_price(-99.99, "USD")
        assert result == "$-99.99"
    
    def test_format_large_number(self):
        """测试大数值格式化"""
        result = format_stock_price(999999.999, "USD")
        assert result == "$1,000,000.00"
    
    def test_default_currency(self):
        """测试默认货币（USD）"""
        result = format_stock_price(100.0)
        assert result == "$100.00"
    
    def test_invalid_currency(self):
        """测试无效货币，应回退到 USD"""
        result = format_stock_price(100.0, "EUR")
        assert result == "$100.00"


class TestGetStockPrice:
    """测试 get_stock_price 函数"""
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_get_demo_stock_success(self, mock_get_demo):
        """测试成功获取演示股票数据"""
        # 模拟返回数据
        mock_data = {
            "symbol": "AAPL",
            "price": 175.25,
            "currency": "USD",
            "name": "Apple Inc.",
            "change": 1.25,
            "change_percent": 0.72
        }
        mock_get_demo.return_value = mock_data
        
        result = get_stock_price("AAPL", "demo")
        
        assert result == mock_data
        mock_get_demo.assert_called_once_with("AAPL")
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_get_demo_stock_not_found(self, mock_get_demo):
        """测试获取不存在的演示股票"""
        mock_get_demo.return_value = None
        
        result = get_stock_price("INVALID", "demo")
        
        assert result is None
        mock_get_demo.assert_called_once_with("INVALID")
    
    def test_get_stock_invalid_source(self):
        """测试无效数据源，应回退到 demo"""
        # 注意：实际函数中如果 source 不是 "demo"，会回退到 demo
        # 这里我们测试这个行为
        with patch('finance_cli.commands.stock._get_demo_stock_data') as mock_get_demo:
            mock_data = {"symbol": "AAPL", "price": 175.25}
            mock_get_demo.return_value = mock_data
            
            result = get_stock_price("AAPL", "invalid_source")
            
            assert result == mock_data
            mock_get_demo.assert_called_once_with("AAPL")
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_get_stock_empty_symbol(self, mock_get_demo):
        """测试空股票代码"""
        mock_get_demo.return_value = None
        
        result = get_stock_price("", "demo")
        
        assert result is None
        mock_get_demo.assert_called_once_with("")
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_get_stock_lowercase_symbol(self, mock_get_demo):
        """测试小写股票代码（应转换为大写）"""
        mock_data = {"symbol": "AAPL", "price": 175.25}
        mock_get_demo.return_value = mock_data
        
        result = get_stock_price("aapl", "demo")
        
        assert result == mock_data
        # 注意：_get_demo_stock_data 应该接收大写的符号
        mock_get_demo.assert_called_once_with("AAPL")
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_get_stock_with_whitespace(self, mock_get_demo):
        """测试带空格的股票代码"""
        mock_data = {"symbol": "AAPL", "price": 175.25}
        mock_get_demo.return_value = mock_data
        
        result = get_stock_price("  AAPL  ", "demo")
        
        assert result == mock_data
        # 应该去除空格并转换为大写
        mock_get_demo.assert_called_once_with("AAPL")


class TestIntegration:
    """集成测试：组合测试 format_stock_price 和 get_stock_price"""
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_format_from_get_stock_price(self, mock_get_demo):
        """测试从 get_stock_price 获取数据并格式化"""
        # 模拟返回数据
        mock_data = {
            "symbol": "AAPL",
            "price": 175.25,
            "currency": "USD",
            "name": "Apple Inc.",
            "change": 1.25,
            "change_percent": 0.72
        }
        mock_get_demo.return_value = mock_data
        
        # 获取股票数据
        stock_data = get_stock_price("AAPL", "demo")
        
        # 格式化价格
        formatted_price = format_stock_price(
            stock_data["price"], 
            stock_data["currency"]
        )
        
        assert stock_data == mock_data
        assert formatted_price == "$175.25"
    
    @patch('finance_cli.commands.stock._get_demo_stock_data')
    def test_cny_stock_formatting(self, mock_get_demo):
        """测试人民币股票格式化"""
        # 模拟人民币股票数据
        mock_data = {
            "symbol": "000001",
            "price": 12.34,
            "currency": "CNY",
            "name": "平安银行",
            "change": 0.12,
            "change_percent": 0.98
        }
        mock_get_demo.return_value = mock_data
        
        stock_data = get_stock_price("000001", "demo")
        formatted_price = format_stock_price(
            stock_data["price"], 
            stock_data["currency"]
        )
        
        assert formatted_price == "¥12.34"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])