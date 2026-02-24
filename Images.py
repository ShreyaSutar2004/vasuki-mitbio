from PIL import Image

img = Image.open("D:\Shreya_VS_projects\Modeller_automation\Images\MIT BIO Logo.png")
# Strip ICC profile and other metadata
data = list(img.getdata())
clean = Image.new(img.mode, img.size)
clean.putdata(data)
clean.save("MIT_BIO_new_logo_clean.png")