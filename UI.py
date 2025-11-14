import os
from cProfile import label
import tkinter as tk
from tkinter import *
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk

os.environ['TCL_LIBRARY'] = r"C:\Users\twsho\AppData\Local\Programs\Python\Python313\tcl\tcl8.6"
os.environ['TK_LIBRARY'] = r"C:\Users\twsho\AppData\Local\Programs\Python\Python313\tcl\tk8.6"

def UploadAction(event=None):
    global file_path
    file_path = filedialog.askopenfilename(
        title="select source code",
        filetypes=[("Source Files", "*.cpp *.go *.rs"), ("All files", "*.*")]
    )
    if file_path:
        messagebox.showinfo("File Uploaded", f"Uploaded{file_path}")

# --- Flamegraph Window (2nd window)---
def show_flamegraph_screen():
    # --- last window Next button ---
    def next_screen2():
        root.destroy()
        show_visualize_screen()
    flam= tk.Tk()
    flam.title("Visualization LLVMIR to Optimize Low Level Code")
    flam.geometry('800x600')
    flam.config(bg="white")

    tk.Label(flam, text= "Visualization LLVMIR to Optimize Low Level Code",
             font=("Arial", 16, "bold")).pack(pady=10)

    tk.Label(flam, text="Select block to view LLVMIR",
             font=("Arial", 12), bg="white").pack(pady=5)
    next_button = ttk.Button(flam, text="Next", command=lambda: [flam.destroy(), show_visualize_screen()])
    next_button.place(relx=0.5, rely=0.95, anchor="s")
    
    #to change what shows up as the image you would take the file path from the UploadAction and then place
    img = Image.open("flamegraph.png")
    img = img.resize((700, 400))
    photo = ImageTk.PhotoImage(img)
    tk.Label(flam, image=photo).pack()

    flam.mainloop()

# --- Visualization Window (the 3rd window)---
def show_visualize_screen():
    vis = tk.Tk()
    vis.title("Visualization")
    vis.geometry("800x600")
    tk.Label(vis, text="This is the visualization window").pack(pady=20)
    next_button = ttk.Button(vis, text="Next", command=lambda: [vis.destroy(), sequencediagram()])
    next_button.place(relx=0.5, rely=0.95, anchor="s")



    img = Image.open("flamegraphs_simp.png")
    img = img.resize((700, 400))
    photo = ImageTk.PhotoImage(img)
    tk.Label(vis, image=photo).pack()




    vis.mainloop()

def  sequencediagram():
    seq=tk.Tk()
    seq.title("Sequence Diagram")
    seq.geometry("800x600")
    tk.Label(seq, text="Sequence Diagram").pack(pady=20)

    img = Image.open("sequence.png")
    img = img.resize((700, 400))
    photo = ImageTk.PhotoImage(img)
    tk.Label(seq, image=photo).pack()

    seq.mainloop()

# --- Main Window Setup ---
root = Tk()
root.title("LLVMIR Optomization")
root.geometry('650x400')
root.config(bg="white")



#create the step to follow text
# --- Instruction Text ---
steps = """Steps to follow
1. Choose how many optimization steps for your source code.
2. Choose low level language which you are uploading.
3. Upload source code (.cpp, .go, or .rs) 
"""
tk.Label(root, text=steps, justify="left", font=("Arial", 12), bg="white").pack(anchor="w", padx=30, pady=5)


lO= Label(root, text="Choose Optimization Steps:", font=("Arial", 12), bg="white")
#the radioButton
var = IntVar()
R1= Radiobutton(root, text='C++', variable=var,value=1,)
R1.pack(anchor="e", pady =2)
R2 = Radiobutton(root, text='Go', variable=var,value=2,)
R2.pack(anchor="e", pady =2)
R3 = Radiobutton(root, text='Rust', variable=var,value=3,)
R3.pack(anchor="e", pady =2)

#the upload button
button = tk.Button(root, text='Upload', command=UploadAction)
button.pack(anchor="e", pady =2)

#Combobox (the Dropdown)
steps_var = tk.StringVar()
steps_combo =ttk.Combobox(root, textvariable=steps_var, state='readonly',width=10)

#add values 1 though 5
steps_combo['values'] = ('1', '2', '3', '4', '5')
steps_combo.current(0)#the default is 1

# Function to print selected step
def show_selected():
    print(f"Selected optimization step: {steps_var.get()}")

# ---Next Button flame ---
def next_screen():
    root.destroy()
    show_flamegraph_screen()
next_btn = ttk.Button(root, text="Next", command=next_screen)
next_btn.pack(anchor="e")

lO.pack(anchor=W)
steps_combo.pack(anchor=W)
ttk.Button(root, text="Confirm", command=show_selected).pack(anchor=W)


#this will always be last no matter what
root.mainloop()