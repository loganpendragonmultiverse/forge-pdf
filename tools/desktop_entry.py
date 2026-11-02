from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from forge_pdf.app import main

    main()
