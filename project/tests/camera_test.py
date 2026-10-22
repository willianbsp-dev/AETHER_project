import cv2

camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not camera.isOpened():
    camera.release()
    camera = cv2.VideoCapture(1, cv2.CAP_DSHOW)

if not camera.isOpened():
    print("ERRO: nenhuma câmera disponível.")
else:
    print("Câmera aberta! Pressione ESC para fechar.")
    while True:
        ok, frame = camera.read()
        if not ok:
            break
        cv2.imshow("AETHER - Teste da camera", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

camera.release()
cv2.destroyAllWindows()
