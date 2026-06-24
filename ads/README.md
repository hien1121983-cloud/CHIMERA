# Ads Pool

Đặt các file `.jpg` / `.png` quảng cáo (1 slide) vào thư mục này.
Timeline Mapper sẽ chọn ngẫu nhiên 1 file và gắn vào `ad_slot.json` của
mỗi version, cho biết chèn sau scene số mấy + thời lượng đề xuất.

Scene có `no_ad: true` (do LLM gán cho cao trào) sẽ KHÔNG được chọn làm slot.
