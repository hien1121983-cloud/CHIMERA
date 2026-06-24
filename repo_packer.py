import os

def pack_repo(repo_path='.', output_file='chimera_full_source.txt'):
    # Danh sách các thư mục cần bỏ qua để tránh rác
    ignore_dirs = {'.git', '__pycache__', 'venv', 'env', '.idea', '.vscode', 'assets', 'images', 'history'}
    
    # Chỉ gom các file có đuôi mở rộng này (Bỏ qua file mp4, mp3, png...)
    valid_exts = {'.py', '.json', '.yml', '.yaml', '.md', '.txt'}

    print(f"🚀 Bắt đầu gom mã nguồn vào file: {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("================================================================================\n")
        outfile.write("TỔNG HỢP MÃ NGUỒN DỰ ÁN CHIMERA V4.0\n")
        outfile.write("================================================================================\n\n")

        for root, dirs, files in os.walk(repo_path):
            # Cắt bỏ các thư mục rác khỏi vòng lặp
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in valid_exts:
                    # Bỏ qua chính file output và file script này
                    if file == output_file or file == 'repo_packer.py':
                        continue
                        
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, repo_path)
                    
                    # Đóng dấu phân cách để LLM dễ nhận diện file
                    outfile.write(f"\n{'='*80}\n")
                    outfile.write(f"FILE: {rel_path}\n")
                    outfile.write(f"{'='*80}\n")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            outfile.write(infile.read())
                            outfile.write("\n")
                        print(f"✅ Đã gom: {rel_path}")
                    except Exception as e:
                        outfile.write(f"# LỖI KHÔNG ĐỌC ĐƯỢC FILE NÀY: {e}\n")
                        print(f"❌ Lỗi: {rel_path}")

    print(f"🎉 Hoàn tất! Hãy upload file '{output_file}' lên cho hệ thống LLM.")

if __name__ == "__main__":
    pack_repo()
  
