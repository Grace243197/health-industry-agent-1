"""
html_extract.py · HTML文本提取脚本

功能：
  - 从HTML文件中提取纯文本内容
  - 去除HTML标签、脚本、样式等
  - 保留标题结构（转换为Markdown格式）
  - 支持批量处理

使用：
  python tools/html_extract.py <input.html> [output.md]
  python tools/html_extract.py --batch <directory>

不联网；不调用模型；纯本地处理。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from html.parser import HTMLParser


class HTMLTextExtractor(HTMLParser):
    """HTML文本提取器，保留标题结构"""
    
    # 需要跳过的标签
    SKIP_TAGS = {'script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript'}
    
    # 标题标签映射
    HEADING_TAGS = {'h1': '# ', 'h2': '## ', 'h3': '### ', 'h4': '#### ', 'h5': '##### ', 'h6': '###### '}
    
    # 块级标签（添加换行）
    BLOCK_TAGS = {'p', 'div', 'br', 'hr', 'li', 'tr', 'blockquote', 'pre', 'article', 'section'}
    
    def __init__(self):
        super().__init__()
        self.result = []
        self.current_tag = None
        self.skip_depth = 0
        self.in_pre = False
        
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        
        # 检查是否在跳过区域
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
            
        if self.skip_depth > 0:
            return
        
        # 处理标题
        if tag in self.HEADING_TAGS:
            self.result.append('\n\n' + self.HEADING_TAGS[tag])
            self.current_tag = tag
            
        # 处理块级元素
        elif tag in self.BLOCK_TAGS:
            self.result.append('\n')
            if tag == 'li':
                self.result.append('- ')
            elif tag == 'br':
                self.result.append('\n')
            elif tag == 'hr':
                self.result.append('\n---\n')
                
        # 处理链接
        elif tag == 'a':
            href = dict(attrs).get('href', '')
            if href and not href.startswith('#'):
                self.result.append('[')
                self.current_tag = 'a'
                
        # 处理粗体
        elif tag in ('strong', 'b'):
            self.result.append('**')
            self.current_tag = 'strong'
            
        # 处理斜体
        elif tag in ('em', 'i'):
            self.result.append('*')
            self.current_tag = 'em'
            
        # 处理pre标签
        elif tag == 'pre':
            self.in_pre = True
            self.result.append('\n```\n')
            
        elif tag == 'code':
            if not self.in_pre:
                self.result.append('`')
    
    def handle_endtag(self, tag):
        tag = tag.lower()
        
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
            
        if self.skip_depth > 0:
            return
        
        if tag in self.HEADING_TAGS:
            self.result.append('\n')
            self.current_tag = None
            
        elif tag == 'a':
            self.current_tag = None
            
        elif tag in ('strong', 'b'):
            self.result.append('**')
            self.current_tag = None
            
        elif tag in ('em', 'i'):
            self.result.append('*')
            self.current_tag = None
            
        elif tag == 'pre':
            self.in_pre = False
            self.result.append('\n```\n')
            
        elif tag == 'code':
            if not self.in_pre:
                self.result.append('`')
                
        elif tag in self.BLOCK_TAGS:
            self.result.append('\n')
    
    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        self.result.append(data)
    
    def get_text(self) -> str:
        """获取提取的文本"""
        text = ''.join(self.result)
        # 清理多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def extract_text_from_html(html_content: str) -> str:
    """从HTML内容提取纯文本"""
    extractor = HTMLTextExtractor()
    extractor.feed(html_content)
    return extractor.get_text()


def extract_title_from_html(html_content: str) -> str:
    """从HTML内容提取标题"""
    # 尝试从<title>标签提取
    match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE | re.DOTALL)
    if match:
        title = match.group(1).strip()
        # 清理标题
        title = re.sub(r'\s*[-|–—].*$', '', title)  # 移除网站名称后缀
        return title
    
    # 尝试从第一个<h1>提取
    match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    
    return "Unknown Title"


def process_html_file(input_path: Path, output_path: Path = None) -> tuple[str, str]:
    """处理单个HTML文件，返回(标题, 提取的文本)"""
    html_content = input_path.read_text(encoding='utf-8', errors='ignore')
    
    # 提取标题
    title = extract_title_from_html(html_content)
    
    # 提取文本
    text = extract_text_from_html(html_content)
    
    # 添加元信息
    result = f"# {title}\n\n> 来源: {input_path.name}\n\n---\n\n{text}"
    
    # 写入文件
    if output_path:
        output_path.write_text(result, encoding='utf-8')
        print(f"已提取: {input_path.name} -> {output_path.name}")
        print(f"  标题: {title}")
        print(f"  字数: {len(text)}")
    
    return title, text


def batch_process(directory: Path, output_dir: Path = None):
    """批量处理目录下的所有HTML文件"""
    html_files = list(directory.glob('*.html')) + list(directory.glob('*.htm'))
    
    if not html_files:
        print(f"未找到HTML文件: {directory}")
        return
    
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"找到 {len(html_files)} 个HTML文件")
    print("-" * 50)
    
    results = []
    for html_file in html_files:
        output_path = None
        if output_dir:
            output_path = output_dir / f"{html_file.stem}.md"
        
        try:
            title, text = process_html_file(html_file, output_path)
            results.append({
                'file': html_file.name,
                'title': title,
                'chars': len(text),
                'output': str(output_path) if output_path else None
            })
        except Exception as e:
            print(f"错误: {html_file.name}: {e}")
    
    print("-" * 50)
    print(f"处理完成: {len(results)} 个文件")
    
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description='从HTML文件提取纯文本')
    ap.add_argument('input', nargs='?', help='输入HTML文件路径')
    ap.add_argument('output', nargs='?', help='输出Markdown文件路径（可选）')
    ap.add_argument('--batch', '-b', action='store_true', help='批量处理目录')
    ap.add_argument('--output-dir', '-o', type=str, help='批量处理输出目录')
    ap.add_argument('--stdout', action='store_true', help='输出到标准输出')
    
    args = ap.parse_args()
    
    if args.batch:
        # 批量处理模式
        if not args.input:
            args.input = '.'
        directory = Path(args.input)
        if not directory.is_dir():
            print(f"错误: 不是目录: {directory}", file=sys.stderr)
            return 1
        
        output_dir = Path(args.output_dir) if args.output_dir else None
        batch_process(directory, output_dir)
        
    elif args.input:
        # 单文件处理模式
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"错误: 文件不存在: {input_path}", file=sys.stderr)
            return 1
        
        if args.output:
            output_path = Path(args.output)
            process_html_file(input_path, output_path)
        elif args.stdout:
            title, text = process_text_from_html(input_path)
            print(f"# {title}\n\n{text}")
        else:
            # 默认输出到同名.md文件
            output_path = input_path.with_suffix('.md')
            process_html_file(input_path, output_path)
    
    else:
        ap.print_help()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
